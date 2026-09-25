"""Processo "quente" de compra de UMA viagem da Config (PLANO_FINAL.md 3.3, 3.3.1, 3.10).

Lançado pelo Scheduler (scheduler.py) uns minutos antes do instante T-24h:

    python scripts/hot_buy.py --date 2026-09-22 --leg v12

Linha temporal:
    T-6min  arranque; pre-flight (3.10.4) e notificação de estado
    T-5min  login na CP (o único do disparo, 3.1) e pesquisa das secções do comboio
    até T   mantém a ligação TCP/TLS quente; espera de precisão com
            time.monotonic() sobre o relógio sincronizado por chrony
    T       UM único POST /sale (retry só pela política de 3.3.1)
    depois  passageiro -> cliente -> fiscal -> desconto do passe -> confirmar,
            com estado guardado em cada passo (retoma após reboot, 3.10.6)

Nada aqui falha em silêncio: todo o desfecho gera notificação (popup) e linha
na aba Logs; erros inesperados também.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Callable

import common
from common import (STATES, TERMINAL, TZ, Leg, PurchaseLock, app_config, get_logger,
                    notify, notify_once, short_hash, station_code)
from cp_ticket import (CPClient, CPError, classify_sale_response, login, pick_aisle_seats, pick_trip,
                       refresh_tokens, trip_sections)
import pre_flight
import timetable

log = get_logger("hot_buy")

RESUMABLE = {"SALE_CREATED", "PASSENGERS_OK", "CLIENT_OK", "FISCAL_OK", "DISCOUNT_OK"}
STEPS = ("PASSENGERS_OK", "CLIENT_OK", "FISCAL_OK", "DISCOUNT_OK", "CONFIRMED")
MAX_STARTS = 4  # relançamentos automáticos de um processo que morreu a meio


def cfg(name: str, default: Any) -> Any:
    return app_config().get("purchase", {}).get(name, default)


def sold_out_delays() -> list[float]:
    """Esperas entre tentativas quando a CP diz «esgotado» (a 1.ª tentativa não espera). Por fases `[duração_s, intervalo_s]`
    (`sold_out_phases`): denso no início — é quando um lugar libertado (venda cancelada por outro) tem mais hipóteses de aparecer
    (ensaio de 24/09: apareceu um lugar ao fim de ~30 s) — e cada vez mais espaçado, sempre abaixo do limite da CP (429 a ~120 pedidos
    em ~30 s). Uma lista explícita `sold_out_retry_delays_s` (incluindo `[]` = sem rajada) tem prioridade, para testes e afinações."""
    explicita = app_config().get("purchase", {}).get("sold_out_retry_delays_s")
    if explicita is not None:
        return [float(x) for x in explicita]
    fases = cfg("sold_out_phases", [[10, 0.5], [50, 1.0], [240, 3.0], [600, 10.0]])
    return [float(iv) for dur, iv in fases for _ in range(max(0, round(float(dur) / float(iv))))]


def hms(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%H:%M:%S.") + f"{int(ts * 1000) % 1000:03d}"


def find_key(obj: Any, key: str) -> Any:
    """Procura recursivamente `key` num JSON (a estrutura de seatData não é garantida)."""
    if isinstance(obj, dict):
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        for v in obj.values():
            r = find_key(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_key(v, key)
            if r is not None:
                return r
    return None


def collect_seats(obj: Any) -> list[dict]:
    """Todos os lugares atribuídos (carruagem + lugar), por ordem. Numa viagem com transbordo há um por
    comboio (ex.: 511 e 4609): o `trainNumber` que identifica cada lugar é o do bloco que o contém
    (`outwardTrip[i]`), não o da própria `seatData`, por isso o número desce durante a travessia."""
    found: list[dict] = []

    def walk(o: Any, train: Any = None) -> None:
        if isinstance(o, dict):
            train = o.get("trainNumber", train)
            c, s = o.get("carriageNumber"), o.get("seatNumber")
            if c not in (None, "") and s not in (None, ""):
                x = {"carriage": c, "seat": s, "train": train}
                if x not in found:
                    found.append(x)
            for v in o.values():
                walk(v, train)
        elif isinstance(o, list):
            for v in o:
                walk(v, train)

    walk(obj)
    return found


def seat_phrase(seats: list[dict]) -> str:
    parts = []
    for x in seats:
        bit = f"carruagem {x['carriage']}, lugar {x['seat']}"
        parts.append(bit + (f" (comboio {x['train']})" if len(seats) > 1 and x.get("train") else ""))
    return " · ".join(parts)


def merge_seats(base: list[dict], extra: list[dict]) -> list[dict]:
    """União de duas listas de lugares por comboio: `extra` (mais recente) sobrepõe-se a `base` só
    para os comboios que também traz; os que só estão em `base` mantêm-se."""
    order: list[Any] = []
    by_train: dict[Any, dict] = {}
    for lst in (base, extra):
        for x in lst:
            k = x.get("train")
            if k not in by_train:
                order.append(k)
            by_train[k] = x
    return [by_train[k] for k in order]


def to_amount(v: Any) -> float | None:
    if isinstance(v, dict):
        for k in ("value", "amount", "total"):
            if k in v:
                return to_amount(v[k])
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    # A CP devolve "€ 0,00" / "€ 23,45" (símbolo, espaço, vírgula decimal). Até 24/09/2026 isto dava None e a
    # guarda «total ≠ 0 → não confirmar» nunca chegou a funcionar (só saía o aviso «totalAmount não encontrado»).
    t = re.sub(r"[^0-9,.\-]", "", str(v))
    if not t or not re.search(r"\d", t):
        return None
    if "," in t and "." in t:                       # 1.234,56 (milhares com ponto, decimais com vírgula)
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def already_bought(sheets_client: Any, leg: Leg) -> bool:
    """A viagem já consta em Bilhetes? Protege contra comprar duas vezes (Buyer e PedidoAttempt)."""
    try:
        rows = sheets_client.read_tickets()
    except Exception as e:  # noqa: BLE001
        log.error("Não consegui verificar duplicados na Sheet: %s", type(e).__name__)
        notify_once("dup-check-failed", "Não consegui verificar compras anteriores",
                    "Falhou a leitura da aba Bilhetes; o bloqueio local por lock continua ativo.",
                    cooldown_s=3600, logger=log)
        return False
    for r in rows:
        r = list(r) + [""] * 2
        d = common.parse_sheet_date(r[0])
        try:
            train = int(float(r[1]))
        except (TypeError, ValueError):
            continue
        if d == leg.date and train == leg.train:
            return True
    return False


class SeatMixin:
    """Preferência de lugar (ao corredor), partilhada pelo `Buyer` (T-24h) e pelo `PedidoAttempt` (pedidos avulsos)."""

    def improve_seat(self, sale_id: Any) -> None:
        """Preferência de lugar (por omissão «corredor»; `seat_preference` = aisle|none): com a venda RETIDA antes de T, muda o
        lugar atribuído para um livre ao corredor (`PUT /train-seats`, testado a 24/09/2026). Nunca faz falhar a compra: qualquer
        erro fica em log e a compra segue com o lugar que a CP deu. Se isto vier a atrapalhar, desliga-se com
        `seat_preference: "none"` (decisão de 24/09: seguir o comportamento e retirar se falhar por causa disto)."""
        if str(cfg("seat_preference", "aisle")).lower() not in ("aisle", "corredor"):
            return
        try:
            seats = list(self.lock.state.get("seats") or [])
            for cur in seats:
                train = cur.get("train") or self.leg.train
                if cur.get("carriage") in (None, "") or cur.get("seat") in (None, ""):
                    continue
                seat_map = self.cp.get_seat_map(sale_id, train)
                candidatos = pick_aisle_seats(seat_map, int(cur["carriage"]), int(cur["seat"]),
                                              limit=int(cfg("seat_change_max_tries", 4)))
                if not candidatos:
                    log.info("Lugar %s/%s: já é corredor (ou não há corredor livre); não mudo.", cur["carriage"], cur["seat"])
                    continue
                for carriage, seat in candidatos:
                    try:
                        resp = self.cp.change_seat(sale_id, train, int(cur["carriage"]), int(cur["seat"]), carriage, seat)
                    except CPError as e:
                        log.info("Lugar %s/%s ocupado ou recusado (%s); tento o seguinte.", carriage, seat,
                                 (e.response.text[:80] if e.response is not None else e))
                        self._tent("lugar", e.response, "recusado" if e.response is not None else "erro", detalhe=f"{carriage}/{seat}")
                        continue
                    self._tent("lugar", resp, "ok", detalhe=f"{cur['carriage']}/{cur['seat']} -> {carriage}/{seat}")
                    novo = dict(cur, carriage=carriage, seat=seat)
                    seats = [novo if s is cur else s for s in seats]
                    self.lock.update(seats=seats, carriage=(seats[0]["carriage"] if len(seats) == 1 else self.lock.state.get("carriage")),
                                     seat=(seats[0]["seat"] if len(seats) == 1 else self.lock.state.get("seat")),
                                     seat_changed=f"{cur['carriage']}/{cur['seat']} → {carriage}/{seat} (corredor)",
                                     seat_target=f"{carriage}/{seat}")
                    log.info("Lugar mudado para o corredor: %s/%s → %s/%s (%.0f ms)", cur["carriage"], cur["seat"], carriage, seat,
                             resp.elapsed_ms)
                    break
        except Exception as e:  # noqa: BLE001 — a preferência nunca pode estragar a compra
            log.warning("Preferência de lugar falhou (%s: %s); sigo com o lugar atribuído.", type(e).__name__, e)

    # ---- registo dos pedidos à CP (tabela bilhetes_tentativas), em memória e gravado no fim da compra ----------------

    def _tent(self, fase: str, resp: Any, resultado: str, *, target: float | None = None, codigo: str = "", detalhe: str = "") -> None:
        """Junta um pedido à CP ao registo desta compra. Só memória: nunca escreve na base no caminho crítico nem falha."""
        try:
            buf = self.__dict__.setdefault("_tents", [])
            if len(buf) >= 1500:
                return
            enviado = getattr(resp, "sent_at", None) or self.clock()
            corpo = resp.body if isinstance(getattr(resp, "body", None), dict) else {}
            buf.append({"ts": datetime.fromtimestamp(enviado, TZ).isoformat(timespec="milliseconds"),
                        "data_viagem": self.leg.date.isoformat(), "perna": self.leg.leg, "comboio": self.leg.train, "fase": fase,
                        "http": getattr(resp, "status", None), "resultado": resultado,
                        "rel_t_ms": round((enviado - target) * 1000) if target is not None else None,
                        "rtt_ms": round(resp.elapsed_ms) if resp is not None and hasattr(resp, "elapsed_ms") else None,
                        "ligacao_nova": {True: 1, False: 0}.get(getattr(resp, "new_conn", None)),
                        "ts_cp": str(corpo.get("timestamp") or ""), "codigo": str(codigo or corpo.get("error") or "")[:40],
                        "detalhe": str(detalhe)[:200]})
        except Exception:  # noqa: BLE001 — diagnóstico, nunca estraga a compra
            pass

    def flush_tentativas(self) -> None:
        """Grava o registo desta compra (uma transação), fora do caminho crítico. Sem suporte na base (Sheets) ou em erro: só log."""
        buf = self.__dict__.get("_tents") or []
        if not buf:
            return
        self.__dict__["_tents"] = []
        try:
            grava = getattr(self._sheets(), "append_attempts", None)
            if grava is not None:
                grava(buf)
        except Exception as e:  # noqa: BLE001
            log.warning("Não consegui gravar o registo de %d pedidos à CP: %s: %s", len(buf), type(e).__name__, e)

    def seat_note(self, carriage: Any, seat: Any) -> tuple[str, str]:
        """(sufixo para a mensagem, aviso). Compara o lugar do bilhete com o que pedimos ao corredor: o sufixo é « (corredor)» se
        o bilhete o reflete; o aviso diz o que aconteceu se a CP devolveu OUTRO lugar (a confirmar no 1.º disparo real)."""
        alvo = self.lock.state.get("seat_target")
        if not alvo:
            return "", ""
        if f"{carriage}/{seat}" == alvo:
            return " (corredor)", ""
        return "", f" ⚠️ pedi o lugar {alvo} (corredor) mas o bilhete diz {carriage}/{seat}"


class Buyer(SeatMixin):
    def __init__(self, leg: Leg, lock: PurchaseLock, *, sheets: Any = None,
                 login_fn: Callable[[], dict] = login,
                 refresh_fn: Callable[[str], dict] = refresh_tokens,
                 cp_factory: Callable[[str], CPClient] = CPClient,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 notify_fn: Callable[..., bool] = notify) -> None:
        self.leg = leg
        self.lock = lock
        self.sheets = sheets
        self.login_fn, self.refresh_fn, self.cp_factory = login_fn, refresh_fn, cp_factory
        self.clock, self.sleep, self.notify = clock, sleep, notify_fn
        self.cp: CPClient | None = None
        self.tokens: dict = {}
        self.login_at = 0.0
        self.origin_code = station_code(leg.origin) or ""
        self.dest_code = station_code(leg.destination) or ""
        rota = f"{common.station_label(leg.origin)}→{common.station_label(leg.destination)}"
        self.label = f"comboio {leg.train} ({rota}) {leg.date.strftime('%d/%m')} {leg.hhmm}"

    # ---- utilitários ----------------------------------------------------

    @property
    def fire_ts(self) -> float:
        return self.leg.fire.timestamp() + float(cfg("fire_offset_ms", 0)) / 1000.0

    def _sheets(self):
        if self.sheets is None:
            self.sheets = common.get_store()
        return self.sheets

    def sheet(self, method: str, *args: Any, **kwargs: Any) -> bool:
        """Escreve na Sheet sem nunca interromper a compra; a falha fica visível."""
        try:
            getattr(self._sheets(), method)(*args, **kwargs)
            return True
        except Exception as e:  # noqa: BLE001 — qualquer erro de Sheets é não-fatal aqui
            log.error("Sheet (%s) falhou: %s: %s", method, type(e).__name__, e)
            notify_once(f"sheet-write-{short_hash(type(e).__name__)}",
                        "Não consegui escrever na Sheet",
                        f"A compra continua, mas a escrita em {method} falhou ({type(e).__name__}). "
                        "Confirma a partilha da Sheet com a service account.",
                        cooldown_s=3600, logger=log)
            return False

    def slog(self, tipo: str, resultado: str, *, status: Any = "", ref: str = "", err: str = "") -> None:
        self.sheet("append_log", tipo, self.leg.date.isoformat(), self.leg.leg, self.leg.train,
                   status, resultado, ref, err)

    def wait_until(self, ts: float, keepalive: bool = False) -> None:
        """Espera (grosso) até `ts`; com keepalive mantém a ligação e o token vivos."""
        last_ping = 0.0
        while True:
            remaining = ts - self.clock()
            if remaining <= 0:
                return
            if keepalive and self.cp is not None:
                now = self.clock()
                if now - last_ping >= float(cfg("warm_interval_s", 10)) and remaining > 0.5:
                    self.cp.warm(self.leg.train, self.leg.date.isoformat())
                    last_ping = now
                if now - self.login_at > 240 and remaining > 10:
                    self.reauth(quiet=True)
            self.sleep(min(remaining, 1.0 if keepalive else 5.0))

    def precise_wait(self, ts: float) -> None:
        """Espera de precisão: converte o alvo para time.monotonic() nos últimos ~2s
        (imune a saltos do relógio) e faz busy-wait nos últimos milissegundos."""
        while ts - self.clock() > 2.0:
            self.sleep(min(ts - self.clock() - 2.0, 1.0))
        mono_target = time.monotonic() + (ts - self.clock())
        while True:
            left = mono_target - time.monotonic()
            if left <= 0:
                return
            if left > 0.02:
                time.sleep(left - 0.015)

    # ---- terminar -------------------------------------------------------

    REQUEST_ESTADO = {"SOLD_OUT": "ESGOTADO", "FAILED": "FALHOU", "AMBIGUOUS": "AMBIGUO"}

    def terminate(self, state: str, title: str, message: str, tipo: str, *, tags: list[str] | None = None,
                  status: Any = "", ref: str = "") -> int:
        self.lock.update(state=state, final_message=message)
        log.error("%s | %s | %s", state, title, message) if state != "CONFIRMED" else log.info("%s | %s", title, message)
        self.slog(tipo, state, status=status, ref=ref, err="" if state == "CONFIRMED" else message)
        self.notify(title, message, tags=tags or ["warning"], logger=log)
        # Uma viagem da Config que esgota a validação/retry e ainda tem tempo para comprar é
        # espelhada para a fila de Pedidos (3.2.1) — lá pode ser forçada ou agendada, mais leve,
        # sem repetir sozinha aqui (decisão de Bruno, 22/09).
        if state in self.REQUEST_ESTADO and self.leg.departure.timestamp() > time.time():
            leg = self.leg
            pretty = lambda k: k.replace("_", " ").title()  # noqa: E731
            self.sheet("append_request", leg.date.isoformat(), pretty(leg.origin), pretty(leg.destination),
                      leg.train, leg.board or leg.hhmm, ativo="SIM", retry="NAO", estado=self.REQUEST_ESTADO[state])
        return 0 if state in ("CONFIRMED", "SOLD_OUT") else 2

    # ---- fluxo principal ------------------------------------------------

    def run(self) -> int:
        if not self.lock.acquire():
            log.info("%s: já há outro processo a tratar desta compra — a sair.", self.label)
            return 0
        try:
            return self._run()
        except Exception as e:  # noqa: BLE001 — rede de segurança: nada falha calado
            log.error("Erro inesperado: %s\n%s", e, traceback.format_exc())
            notify_once(f"hotbuy-unexpected-{self.leg.lock_key}-{type(e).__name__}",
                        f"Erro inesperado na compra — {self.label}",
                        f"{type(e).__name__}: {e}. Vou tentar retomar automaticamente.",
                        cooldown_s=1800, logger=log)
            self.slog("ERRO", "EXCECAO", err=f"{type(e).__name__}: {e}")
            return 1
        finally:
            self.flush_tentativas()
            self.lock.release()

    def _run(self) -> int:
        st = self.lock.state
        state = st.get("state")
        if state in TERMINAL:
            log.info("%s: já em estado terminal (%s) — nada a fazer.", self.label, state)
            return 0
        starts = int(st.get("starts", 0)) + 1
        self.lock.update(starts=starts, leg=self.leg.key, train=self.leg.train,
                         fire_at=self.leg.fire.isoformat())
        if starts > MAX_STARTS:
            return self.terminate("FAILED", f"Compra abandonada — {self.label}",
                                  f"O processo foi relançado {starts - 1} vezes sem concluir. "
                                  "Verifica na App CP e nos logs.", "ERRO")

        resume = state in RESUMABLE
        if not resume:
            if self.already_bought():
                self.lock.update(state="CONFIRMED", note="já constava em Bilhetes")
                self.notify(f"Já comprado — {self.label}",
                            "Este bilhete já consta na aba Bilhetes; não comprei outra vez.",
                            tags=["white_check_mark"], logger=log)
                return 0
            self.lock.update(state="WARMING")

        # 1) pre-flight e notificação de estado
        self.do_preflight()

        # 2) login (3 min antes) — retoma: imediato
        login_ts = self.leg.fire.timestamp() - float(cfg("login_lead_minutes", 5)) * 60
        self.wait_until(login_ts)
        if not self.login_with_retries(deadline=self.fire_ts - 15):
            return self.terminate("FAILED", f"Login na CP falhou — {self.label}",
                                  "Não consegui autenticar antes do disparo. Confirma a conta/password "
                                  "e se a CP pede algum passo extra.", "ERRO")

        if resume:
            log.info("%s: a retomar a venda %s no estado %s", self.label, st.get("sale_id"), state)
            return self.complete_sale()

        # 3) pesquisa: obter o serviceCode (nunca no caminho crítico)
        if not self.prepare_trip():
            return 2

        # 3b) reter o lugar ANTES de T e só disputar o desconto a T (ver hold_sale); se não for possível, fluxo normal
        if cfg("hold_before_open", True) and self.hold_sale():
            self.improve_seat(self.lock.state["sale_id"])    # lugar ao corredor, com a venda retida (antes de T)
            early = self.complete_sale(pre_only=True)        # passageiro, cliente, fiscal (antes de T)
            if early is not None:
                return early
            return self.complete_sale()                      # espera por T, insiste no desconto e confirma

        # 4) manter a ligação quente e disparar
        self.wait_until(self.fire_ts - 2.0, keepalive=True)
        self.precise_wait(self.fire_ts)
        outcome = self.fire_sale()
        if outcome != "ok":
            return 2 if outcome not in ("sold_out",) else 0
        return self.complete_sale()

    # ---- pre-flight -----------------------------------------------------

    def do_preflight(self) -> None:
        deadline = self.fire_ts - 30
        notified_failure = False
        while True:
            checks = pre_flight.run_preflight(self.leg)
            bad = pre_flight.failed(checks)
            mins = max(0, int((self.leg.fire.timestamp() - self.clock()) / 60))
            when = f"daqui a ~{mins} min" if mins else "agora"
            if not bad:
                pf_ok = pre_flight.check_ntfy(
                    f"Compra {when} — {self.label}",
                    "Pre-flight OK: " + ", ".join(c.name for c in checks) + ".")
                if pf_ok.ok:
                    self.slog("PREFLIGHT", "OK")
                else:  # o próprio ntfy falhou: não há como avisar, por isso fica na Sheet e no log
                    log.error("%s", pf_ok)
                    self.slog("PREFLIGHT", "FALHA", err=pf_ok.detail)
                if notified_failure:
                    self.notify(f"Pre-flight recuperado — {self.label}", "Já está tudo em ordem.",
                                tags=["white_check_mark"], logger=log)
                return
            detail = "; ".join(f"{c.name}: {c.detail}" for c in bad)
            self.slog("PREFLIGHT", "FALHA", err=detail)
            if not notified_failure:
                self.notify(f"Pre-flight com falhas — {self.label}",
                            detail + " — continuo a tentar recuperar até perto do disparo.",
                            tags=["rotating_light"], logger=log)
                notified_failure = True
            if self.clock() >= deadline:
                log.error("Pre-flight ainda com falhas perto do disparo; sigo mesmo assim.")
                return
            self.sleep(20)

    # ---- login e pesquisa ------------------------------------------------

    def login_with_retries(self, deadline: float) -> bool:
        first = True
        while True:
            try:
                self.tokens = self.login_fn()
                self.cp = self.cp_factory(self.tokens["access_token"])
                self.login_at = self.clock()
                self.persist_tokens()
                log.info("Login na CP bem-sucedido.")
                return True
            except Exception as e:  # noqa: BLE001
                log.error("Login na CP falhou: %s: %s", type(e).__name__, e)
                if first:
                    self.notify(f"Login na CP falhou — {self.label}",
                                f"{type(e).__name__}. Vou voltar a tentar até ao disparo.",
                                tags=["warning"], logger=log)
                    first = False
                if self.clock() >= deadline:
                    return False
                self.sleep(5)

    def persist_tokens(self) -> None:
        """Guarda sempre o refresh_token mais recente (o prazo da sessão não desliza; 3.1)."""
        try:
            common.save_tokens(self.tokens)
        except Exception as e:  # noqa: BLE001 — não é crítico para a compra, mas fica registado
            log.warning("Não consegui guardar token.json: %s", type(e).__name__)

    def reauth(self, quiet: bool = False) -> None:
        """Renova o token (refresh) e, se falhar, faz login de novo."""
        try:
            self.tokens = self.refresh_fn(self.tokens["refresh_token"])
            self.cp.access_token = self.tokens["access_token"]
            self.login_at = self.clock()
            self.persist_tokens()
            if not quiet:
                log.info("Token renovado.")
        except Exception:  # noqa: BLE001
            self.login_with_retries(deadline=self.clock() + 20)

    def prepare_trip(self) -> bool:
        cache_path = common._state_file("trains.json")
        trains = common._read_json(cache_path, {})
        ckey = f"{self.leg.train}|{self.leg.origin}|{self.leg.destination}"
        try:
            journeys = self.cp.search_journeys(self.origin_code, self.dest_code, self.leg.date.isoformat())
            trip = pick_trip(journeys, train_number=self.leg.train, require_saleable=False)
            sections = trip_sections(trip, self.origin_code, self.dest_code)
            trains[ckey] = sections
            common._write_json_atomic(cache_path, trains)
            dep = str(trip.get("departureTime", ""))[:5]
            if dep and dep not in (self.leg.hhmm, self.leg.board):
                notify_once(f"hora-mismatch-{self.leg.key}-{dep}",
                            f"Hora não bate certo — {self.label}",
                            f"A Sheet diz {self.leg.hhmm} mas a CP indica {dep} para o comboio "
                            f"{self.leg.train}. Compro pelo nº do comboio; confirma a hora.",
                            cooldown_s=86400, logger=log)
        except (CPError, RuntimeError, KeyError, TypeError) as e:
            log.error("Pesquisa falhou: %s: %s", type(e).__name__, e)
            sections = trains.get(ckey)
            if sections is None:
                self.terminate("FAILED", f"Não encontrei o comboio — {self.label}",
                               f"{e}. Sem dados do serviço não consigo comprar; verifica nº e data.",
                               "ERRO")
                return False
            self.notify(f"Pesquisa falhou — {self.label}",
                        "Vou comprar com o serviço guardado da última vez que este comboio foi pesquisado.",
                        tags=["warning"], logger=log)
        self.lock.update(sections=sections)
        return True

    # ---- disparo ---------------------------------------------------------

    def fire_sale(self) -> str:
        """O disparo. Um erro técnico repete-se pouco (3.3.1); uma venda que ainda NÃO abriu repete-se
        na iteração seguinte, sem criar nada (decisão de Bruno, 22/09): de 0,25 em 0,25 s no início
        e de 2 em 2 s depois, até abrir, esgotar ou acabar a janela. Uma recusa não reconhecida repete-se
        só durante uns segundos (pode ser "ainda não aberto" com outro texto) e depois falha, com a
        resposta completa no log para se aprender o formato. Um "esgotado" (WS:RES:116, ou outro código
        da mesma família — 114, etc.) confirma-se com uma rajada antes de desistir (Bruno, 22/09, tão
        persistente quanto ele já faz à mão — ~12 min): o mesmo código pode aparecer com a rede
        condicionada, sem ser esgotado a sério; como o servidor respondeu SEM criar venda, repetir é tão
        seguro como um erro técnico transitório."""
        st = self.lock.state
        max_attempts = int(cfg("max_sale_attempts", 3))
        esperas_esgotado = sold_out_delays()
        target = self.fire_ts
        open_window = float(cfg("not_open_retry_window_s", 600))
        fast_s, fast_iv = float(cfg("not_open_fast_phase_s", 20)), float(cfg("not_open_fast_interval_s", 0.25))
        slow_iv = float(cfg("not_open_slow_interval_s", 2.0))
        unknown_s = float(cfg("unrecognized_4xx_retry_s", 15))
        departure_ts = self.leg.departure.timestamp()
        attempt = transient = sold_out_retry = 0
        waiting_since: float | None = None
        while True:
            attempt += 1
            if self.clock() - self.login_at > 240:      # o token dura 5 min (3.1); a rajada do esgotado
                self.reauth(quiet=True)                  # pode passar disso — nunca usar um token stale
            try:
                resp = self.cp.create_sale_request(self.leg.date.isoformat(), st["sections"])
            except CPError as e:
                if e.kind == "not_sent" and transient < max_attempts - 1:
                    transient += 1
                    log.warning("POST /sale não chegou a sair (%s) — retry seguro %d/%d", e, transient, max_attempts)
                    self.sleep(0.25 * transient)
                    continue
                if e.kind == "not_sent":
                    self.terminate("FAILED", f"Compra falhou — {self.label}",
                                   f"Sem ligação à CP no disparo ({e}).", "ERRO")
                    return "failed"
                # AMBÍGUO: o pedido pode ter sido entregue -> nunca repetir às cegas
                self.terminate("AMBIGUOUS", f"Estado AMBÍGUO — {self.label}",
                               "O pedido de compra pode ter chegado à CP mas perdi a resposta. "
                               "NÃO repeti. Confirma na App CP se o bilhete existe.",
                               "ERRO", tags=["question"])
                return "ambiguous"

            kind, detail = classify_sale_response(resp)
            timing = self._timing_txt(resp, target)
            self._tent("venda", resp, kind, target=target, detalhe=detail)
            if kind not in ("not_open", "known") or attempt <= 3 or attempt % 20 == 0:   # sem inundar o log
                log.info("POST /sale #%d -> HTTP %s [%s] %s", attempt, resp.status, kind, timing)
            if kind == "ok":
                late = f" | abriu {self.clock() - target:.1f} s depois do alvo, tentativa {attempt}" if waiting_since else ""
                self._sale_created(resp, timing + late)
                return "ok"
            if kind == "transient":
                transient += 1
                if transient < max_attempts:
                    self.sleep(0.25 * transient)
                    continue
            elif kind == "sold_out":
                if sold_out_retry < len(esperas_esgotado) and self.clock() < departure_ts:
                    self.sleep(esperas_esgotado[sold_out_retry])
                    sold_out_retry += 1
                    continue
                mins = sum(esperas_esgotado) / 60
                confirmado = (f" (confirmado depois de {sold_out_retry + 1} tentativas em "
                             f"~{mins:.0f} min)" if esperas_esgotado else "")
                self.terminate("SOLD_OUT", f"Esgotado — {self.label}",
                               f"Não há lugares{confirmado}. {detail}", "COMPRA", tags=["no_entry"],
                               status=resp.status)
                return "sold_out"
            elif kind in ("not_open", "known"):
                now = self.clock()
                window = open_window if kind == "not_open" else unknown_s
                if now < target + window and now < departure_ts:
                    if waiting_since is None:
                        waiting_since = now
                        log.warning("Venda ainda não aberta (%s): resposta %s", kind, common.sanitize(resp.text[:500]))
                        self.slog("COMPRA", "AINDA_NAO_ABERTO" if kind == "not_open" else "RECUSA_A_REPETIR",
                                  status=resp.status, err=f"{detail[:200]} | {timing}")
                        self.notify(f"Ainda não abriu — {self.label}",
                                    ("A CP diz que a venda ainda não abriu" if kind == "not_open" else
                                     "A CP recusou o pedido (resposta não reconhecida; pode ser \"ainda não aberto\")")
                                    + f". Volto a tentar de {fast_iv:g} em {fast_iv:g} s durante até "
                                      f"{window / 60 if window >= 60 else window:.0f} {'min' if window >= 60 else 's'}. "
                                    f"Resposta: {detail[:120]}", tags=["hourglass_flowing_sand"], logger=log)
                    self.sleep(fast_iv if now - target < fast_s else slow_iv)
                    continue
                if kind == "not_open":
                    self.terminate("FAILED", f"A venda não abriu — {self.label}",
                                   f"Tentei durante {open_window / 60:.0f} min e a CP continuou a dizer que "
                                   f"a venda não abriu ({detail[:150]}). Verifica na App CP.", "ERRO",
                                   status=resp.status)
                    return "failed"
            self.terminate("FAILED", f"Compra falhou — {self.label}",
                           f"{detail}. Resposta: {resp.text[:300]}", "ERRO", status=resp.status)
            return "failed"

    def _sale_created(self, resp: Any, timing: str) -> None:
        """Regista a venda criada (lugar atribuído, estado, log) — comum ao disparo a T e à retenção antes de T."""
        sale_id = resp.body["saleID"]
        seats = collect_seats(resp.body)
        self.lock.update(seats=seats, carriage=(seats[0]["carriage"] if seats else find_key(resp.body, "carriageNumber")),
                         seat=(seats[0]["seat"] if seats else find_key(resp.body, "seatNumber")))
        self.lock.update(state="SALE_CREATED", sale_id=sale_id, timing=timing)
        self.slog("COMPRA", "SALE_CREATED", status=resp.status, ref=str(sale_id), err=timing)

    @staticmethod
    def _timing_txt(resp: Any, target: float | None = None) -> str:
        """Linha de diagnóstico de um pedido: quando saiu, quanto demorou e — o que faltava — se abriu uma ligação nova."""
        alvo = f"alvo {hms(target)} | " if target is not None else ""
        rel = f" ({(resp.sent_at - target) * 1000:+.0f} ms)" if target is not None else ""
        ligacao = {True: "ligação NOVA", False: "ligação reutilizada"}.get(getattr(resp, "new_conn", None), "ligação ?")
        srv = resp.body.get("timestamp") if isinstance(resp.body, dict) else None
        return (f"{alvo}enviado {hms(resp.sent_at)}{rel} | resposta {hms(resp.received_at)} ({resp.elapsed_ms:.0f} ms) | "
                f"{ligacao} | timestamp CP {srv} | Date CP {resp.date_header}")

    # ---- reter o lugar ANTES de T e disputar só o desconto (24/09/2026) ------------
    #
    # Medido no Pi: o POST /sale aceita-se dias antes de T (lugar atribuído, 23,45 € pendente), mas o desconto do passe
    # (PUT items, código 302) só passa a ser aceite a T (antes: 500 «SIV:DIS:I:302 Sale item not available»). Por isso
    # segura-se o lugar uns minutos antes e a corrida a T fica reduzida a UM pedido leve numa ligação viva, em vez de
    # disputar o POST /sale com todos os outros compradores. Uma venda pendente que nunca chega a ser confirmada não
    # custa nada e cancela-se com DELETE.

    def hold_sale(self) -> bool:
        """Cria a venda `hold_lead_seconds` antes de T. Devolve True se o lugar ficou retido; False (sem terminar nada)
        se não foi possível — então o fluxo normal a T (com a rajada do esgotado) continua como antes."""
        lead = float(cfg("hold_lead_seconds", 600))
        deadline = self.fire_ts - 3.0
        if self.clock() >= deadline:
            return False                        # sem tempo (arranque atrasado): fluxo normal
        self.wait_until(self.fire_ts - lead, keepalive=True)
        interval = float(cfg("hold_retry_interval_s", 15))
        attempt = 0
        while True:
            attempt += 1
            if self.clock() - self.login_at > 240:
                self.reauth(quiet=True)
            resp = None
            try:
                resp = self.cp.create_sale_request(self.leg.date.isoformat(), self.lock.state["sections"])
            except CPError as e:
                log.warning("Retenção #%d: pedido falhou (%s)", attempt, e)
            if resp is not None:
                kind, detail = classify_sale_response(resp)
                timing = self._timing_txt(resp, self.fire_ts)
                self._tent("retencao", resp, kind, target=self.fire_ts, detalhe=detail)
                if kind == "ok":
                    self._sale_created(resp, f"RETIDA antes de T ({(self.fire_ts - resp.sent_at):.0f} s) | {timing}")
                    log.info("Lugar retido antes de T (tentativa %d): %s", attempt, timing)
                    return True
                log.info("Retenção #%d sem venda [%s]: %s | %s", attempt, kind, detail[:120], timing)
            if self.clock() + interval >= deadline:
                log.warning("Não consegui reter o lugar antes de T; sigo para o disparo normal a T.")
                return False
            self.sleep(interval)

    def cancel_sale(self, sale_id: Any, why: str) -> None:
        """Liberta o lugar de uma venda que sabemos que não vai ser confirmada (nunca em estados incertos)."""
        try:
            r = self.cp.cancel_sale(sale_id)
            log.info("Venda %s cancelada (%s): HTTP %s", sale_id, why, getattr(r, "status", "?"))
        except Exception as e:  # noqa: BLE001 — melhor esforço
            log.warning("Não consegui cancelar a venda %s (%s): %s", sale_id, why, e)

    def race_discount(self, sale_id: Any) -> Any:
        """O desconto do passe (PUT items 302), com insistência à volta de T: antes de T a CP recusa
        (`SIV:DIS:I:302`), a T passa a aceitar. Devolve a resposta aceite; levanta CPError se nunca abrir/for recusado.

        Orçamento de pedidos (a CP responde 429 a ~120 pedidos em ~30 s): de T−0,6 s a T+1,6 s de 0,1 em 0,1 s (com a
        ligação viva cada recusa custa ~50–110 ms), depois de 0,3 em 0,3 s até 48 pedidos, depois 1,5 s. O PUT é
        idempotente, por isso repetir depois de um timeout é seguro."""
        start = self.fire_ts - float(cfg("discount_lead_s", 0.6))
        self.wait_until(start - 2.0, keepalive=True)
        self.precise_wait(start)
        fast_iv, mid_iv = float(cfg("discount_fast_interval_s", 0.10)), float(cfg("discount_mid_interval_s", 0.30))
        slow_iv = float(cfg("discount_slow_interval_s", 1.5))
        fast_until = self.fire_ts + float(cfg("discount_fast_phase_s", 1.6))
        max_fast = int(cfg("discount_max_fast_attempts", 48))
        deadline = min(self.fire_ts + float(cfg("discount_window_s", 180)), self.leg.departure.timestamp())
        unknown_s = float(cfg("discount_unknown_s", 10))
        n = refused = rate_limited = 0
        unknown_since: float | None = None
        last_err: CPError | None = None
        while True:
            n += 1
            if self.clock() - self.login_at > 240:
                self.reauth(quiet=True)
            try:
                resp = self.cp.apply_green_pass(sale_id)
                self._tent("desconto", resp, "ok", target=self.fire_ts)
                log.info("Desconto do passe ACEITE no pedido #%d (recusas antes: %d) | %s", n, refused,
                         self._timing_txt(resp, self.fire_ts))
                self.lock.update(discount_timing=self._timing_txt(resp, self.fire_ts), discount_attempts=n)
                return resp
            except CPError as e:
                last_err = e
                r = e.response
                status = r.status if r is not None else None
                body = r.body if (r is not None and isinstance(r.body, dict)) else {}
                text = (r.text if r is not None else str(e))[:300]
                self._tent("desconto", r, "429" if status == 429 else ("recusado" if body.get("error") == "SIV:DIS:I:302" else "erro"),
                           target=self.fire_ts, detalhe=text[:120])
                if status == 429:
                    rate_limited += 1
                    wait = max(1.0, (r.retry_after_s or 2.0))
                    log.warning("Limite de pedidos da CP (429) no desconto: espero %.1f s (%d)", wait, rate_limited)
                    if rate_limited > 8:
                        raise
                    self.sleep(wait)
                    continue
                if status in (401, 403):
                    self.reauth()
                    if n > 3:
                        raise
                    continue
                if body.get("error") == "SIV:DIS:I:302" or "not available" in text.lower():
                    refused += 1                                   # ainda não abriu (esperado antes de T)
                    unknown_since = None
                    if n <= 3 or n % 20 == 0:
                        log.info("Desconto ainda recusado (#%d): %s", n, self._timing_txt(r, self.fire_ts) if r else "")
                elif e.kind in ("not_sent", "ambiguous") or (status is not None and status >= 500):
                    unknown_since = None                           # erro técnico: o PUT é idempotente, repete-se
                else:                                              # recusa 4xx não reconhecida: só uns segundos
                    unknown_since = unknown_since or self.clock()
                    if self.clock() - unknown_since > unknown_s:
                        raise
            now = self.clock()
            if now >= deadline:
                raise CPError("http", f"o desconto do passe não foi aceite em {n} pedidos (última resposta: "
                                      f"{(last_err.response.text[:150] if last_err and last_err.response else last_err)})",
                              last_err.response if last_err else None)
            if n <= max_fast and now < fast_until:
                self.sleep(fast_iv)
            elif n <= max_fast:
                self.sleep(mid_iv)
            else:
                self.sleep(slow_iv)

    # ---- concluir a venda ------------------------------------------------

    def _step(self, name: str, fn: Callable[[int], Any], sale_id: int):
        # Os PUT são idempotentes: repetir o passo é seguro dentro do prazo da venda
        # (sale_deadline = 15 min). A lista de esperas soma ~12 min.
        delays = list(cfg("step_retry_delays_s", [0.5, 1, 2, 4, 8, 15, 30, 30, 30, 60, 60, 60, 60, 120, 120, 120]))
        ambiguous_seen = False
        for attempt in range(len(delays) + 1):
            if self.clock() - self.login_at > 240:      # access_token dura 5 min (3.1)
                self.reauth(quiet=True)
            try:
                return fn(sale_id)
            except CPError as e:
                status = e.response.status if e.response is not None else None
                last = attempt == len(delays)
                if e.kind == "ambiguous":
                    ambiguous_seen = True
                if status in (401, 403) and not last:
                    self.reauth()
                    continue
                retryable = e.kind in ("not_sent", "ambiguous") or (status is not None and status >= 500)
                if retryable and not last:
                    self.sleep(delays[attempt])
                    continue
                if name == "CONFIRMED" and ambiguous_seen and e.kind == "http":
                    raise CPError("ambiguous", "confirmação incerta após timeout") from e
                raise

    def complete_sale(self, pre_only: bool = False) -> int | None:
        """Passageiro → cliente → fiscal → desconto → confirmar. `pre_only`: pára antes do desconto (a venda foi retida
        antes de T) e devolve None se tudo correu bem."""
        sale_id = self.lock.state["sale_id"]
        done = STATES.index(self.lock.state["state"])
        methods = {"PASSENGERS_OK": self.cp.set_passengers, "CLIENT_OK": self.cp.set_client,
                   "FISCAL_OK": self.cp.set_fiscal, "DISCOUNT_OK": self.cp.apply_green_pass,
                   "CONFIRMED": self.cp.confirm}
        resp = None
        for name in STEPS:
            if STATES.index(name) <= done:
                continue
            if pre_only and name == "DISCOUNT_OK":
                return None
            try:
                resp = self.race_discount(sale_id) if name == "DISCOUNT_OK" else self._step(name, methods[name], sale_id)
            except CPError as e:
                if name == "DISCOUNT_OK":
                    self.cancel_sale(sale_id, "o desconto do passe não foi aceite")
                    return self.terminate("FAILED", f"Desconto do passe não aceite — {self.label}",
                                          f"A CP não aceitou o desconto da venda {sale_id} ({e}). Nada foi confirmado e "
                                          "o lugar foi libertado.", "ERRO")
                if e.kind == "ambiguous" and name == "CONFIRMED":
                    return self.terminate("AMBIGUOUS", f"Confirmação incerta — {self.label}",
                                          f"A venda {sale_id} existe mas não sei se foi confirmada. "
                                          "Confirma na App CP antes de repetir.", "ERRO", tags=["question"])
                return self.terminate("FAILED", f"Venda por concluir — {self.label}",
                                      f"Falhou no passo {name} da venda {sale_id}: {e}. A venda pode "
                                      "expira ao fim de 15 min: conclui na App CP se ainda a vires.",
                                      "ERRO")
            if resp.messages:
                log.warning("Mensagens da CP em %s: %s", name, " | ".join(resp.messages))
            if name == "DISCOUNT_OK":
                total = to_amount(find_key(resp.body, "totalAmount"))
                if total is not None and total != 0.0:
                    self.cancel_sale(sale_id, f"total {total} € depois do desconto")
                    return self.terminate("FAILED", f"Desconto do passe não aplicado — {self.label}",
                                          f"Total da venda {sale_id} ficou {total}€ em vez de 0€. "
                                          "Não confirmei e libertei o lugar. Verifica o passe (validade/número).", "ERRO")
                if total is None:
                    log.warning("totalAmount não encontrado na resposta do desconto; sigo para a confirmação.")
            if name == "CONFIRMED":
                status = resp.body.get("status") if isinstance(resp.body, dict) else None
                status_code = status.get("code") if isinstance(status, dict) else None
                if status_code != "CONFIRMED":
                    return self.terminate("FAILED", f"Venda não confirmada — {self.label}",
                                          f"Estado devolvido pela CP: {status_code!r}.", "ERRO",
                                          status=resp.status)
            self.lock.update(state=name)
        return self.on_confirmed(resp)

    def find_seats(self, body: Any) -> list[dict]:
        """Lugares, por comboio: o `seatData` guardado do `POST /sale` (é aí que o lugar sai, 2.4) é a
        base, e o que o `confirm` trouxer sobrepõe-se, comboio a comboio (uma viagem com transbordo pode
        ter um por secção). Se nenhum dos dois tiver nada, consulta `GET /sales/{id}` em último recurso.
        O lembrete de partida não pode ir sem eles."""
        st = self.lock.state
        seats = merge_seats(list(st.get("seats") or []), collect_seats(body))
        if not seats and st.get("sale_id"):
            try:
                seats = collect_seats(self.cp.get_sale(st["sale_id"]).body)
            except Exception as e:  # noqa: BLE001 — último recurso, nunca impede a confirmação
                log.warning("Não consegui ler a venda %s para obter o lugar: %s", st["sale_id"], type(e).__name__)
        if not seats:                                    # só um dos dois campos, sem "seatData" a envolver
            c = find_key(body, "carriageNumber") or st.get("carriage")
            s_ = find_key(body, "seatNumber") or st.get("seat")
            if c or s_:
                seats = [{"carriage": c, "seat": s_, "train": None}]
        return seats

    def on_confirmed(self, resp: Any) -> int:
        body = resp.body if resp is not None else {}
        ref = str(body.get("reference", "")) if isinstance(body, dict) else ""
        seats = self.find_seats(body)
        complete = [x for x in seats if x["carriage"] not in (None, "") and x["seat"] not in (None, "")]
        carriages = [x["carriage"] for x in seats if x["carriage"] not in (None, "")]
        pieces = [x["seat"] for x in seats if x["seat"] not in (None, "")]
        # com um só lugar mantém o valor tal como veio da CP (não força a string); com vários, junta-os
        carriage = carriages[0] if len(carriages) == 1 else (" / ".join(str(c) for c in carriages) or None)
        seat = pieces[0] if len(pieces) == 1 else (" / ".join(str(p) for p in pieces) or None)
        self.lock.update(reference=ref, carriage=carriage, seat=seat, seats=seats)
        leg = self.leg
        pretty = lambda k: k.replace("_", " ").title()  # noqa: E731
        boarding = leg.board or leg.hhmm                   # hora de embarque real, não a da 1.ª estação
        self.sheet("append_ticket", leg.date.isoformat(), leg.train, pretty(leg.origin),
                   pretty(leg.destination), boarding, carriage or "", seat or "", ref)
        have_seat = bool(complete)
        seat_txt = (seat_phrase(complete) if have_seat else
                    f"carruagem {carriage}" if carriage else f"lugar {seat}" if seat else
                    "carruagem e lugar não devolvidos pela CP — vê na App CP")
        route = f"Comboio {leg.train} · {pretty(leg.origin)} → {pretty(leg.destination)}"
        reminder_ok = False
        remind_ts = leg.departure.timestamp() - 30 * 60          # instante absoluto
        remind_at = datetime.fromtimestamp(remind_ts, TZ)
        if remind_ts > time.time() + 120:
            # carruagem e lugar no TÍTULO e na mensagem: aparecem mesmo num popup truncado
            title = f"Partida às {boarding} · {seat_txt}" if have_seat else f"Partida às {boarding} (daqui a 30 min)"
            reminder_ok = self.notify(title, f"{route}. {seat_txt[0].upper() + seat_txt[1:]}.",
                                      tags=["train"], at=remind_at, logger=log)
        self.lock.update(reminder_scheduled=reminder_ok, seat_known=have_seat)
        extra = "" if reminder_ok else " (lembrete de partida não agendado)"
        nota, aviso = self.seat_note(carriage, seat)
        return self.terminate("CONFIRMED", f"Bilhete comprado — {self.label}",
                              f"{pretty(leg.origin)} → {pretty(leg.destination)} às {boarding} · "
                              f"{seat_txt}{nota} · ref. {ref}{extra}{aviso}", "COMPRA", tags=["white_check_mark"], ref=ref)

    # ---- proteção contra compra duplicada -------------------------------

    def already_bought(self) -> bool:
        return already_bought(self._sheets(), self.leg)


# ---------------------------------------------------------------------------
# Pedido avulso (3.2.1): tentativa leve, sem hotstart nem rajada
# ---------------------------------------------------------------------------

REQUEST_ESTADO = {"CONFIRMED": "CONFIRMADO", "SOLD_OUT": "ESGOTADO", "FAILED": "FALHOU", "AMBIGUOUS": "AMBIGUO"}


class PedidoAttempt(SeatMixin):
    """Uma única tentativa de compra de um pedido avulso (aba Pedidos, 3.2.1): login e compra
    já, sem esperar por T-24h (`leg.fire` já é "agora" para um pedido) e sem hotstart (nada de
    pre-flight nem de login antecipado). No máximo UMA repetição por passo — nunca a rajada de
    ~12 min do esgotado nem os ~16 retries por passo da Config: se falhar, a tentativa acaba já e
    não volta a tentar sozinha (a próxima vez é o intervalo agendado, ou "Tentar agora" outra vez).
    Deliberadamente NÃO reaproveita o `Buyer` (pensado para a precisão ao segundo do T-24h) —
    reaproveita só o `cp_ticket` e os utilitários de lugar/notificação, que são genéricos."""

    def __init__(self, leg: Leg, lock: PurchaseLock, *, sheets: Any = None,
                 login_fn: Callable[[], dict] = login,
                 cp_factory: Callable[[str], CPClient] = CPClient,
                 clock: Callable[[], float] = time.time,
                 sleep: Callable[[float], None] = time.sleep,
                 notify_fn: Callable[..., bool] = notify) -> None:
        self.leg = leg
        self.lock = lock
        self.sheets = sheets
        self.login_fn, self.cp_factory = login_fn, cp_factory
        self.clock, self.sleep, self.notify = clock, sleep, notify_fn
        self.cp: CPClient | None = None
        self.origin_code = station_code(leg.origin) or ""
        self.dest_code = station_code(leg.destination) or ""
        rota = f"{common.station_label(leg.origin)}→{common.station_label(leg.destination)}"
        self.label = f"comboio {leg.train} ({rota}) {leg.date.strftime('%d/%m')} {leg.hhmm} — pedido"

    def _sheets(self):
        if self.sheets is None:
            self.sheets = common.get_store()
        return self.sheets

    def sheet(self, method: str, *args: Any, **kwargs: Any) -> bool:
        try:
            getattr(self._sheets(), method)(*args, **kwargs)
            return True
        except Exception as e:  # noqa: BLE001
            log.error("Sheet (%s) falhou: %s: %s", method, type(e).__name__, e)
            return False

    def slog(self, tipo: str, resultado: str, *, status: Any = "", ref: str = "", err: str = "") -> None:
        self.sheet("append_log", tipo, self.leg.date.isoformat(), self.leg.leg, self.leg.train,
                   status, resultado, ref, err)

    def _update_request(self, **fields: Any) -> None:
        self.sheet("update_request", self.leg.row, ultima_tentativa=datetime.now(TZ).isoformat(timespec="seconds"),
                   **fields)

    def terminate(self, state: str, title: str, message: str, tipo: str, *,
                  tags: list[str] | None = None, status: Any = "", ref: str = "") -> int:
        self.lock.update(state=state, final_message=message)
        (log.error if state != "CONFIRMED" else log.info)("%s | %s | %s", state, title, message)
        self.slog(tipo, state, status=status, ref=ref, err="" if state == "CONFIRMED" else message)
        self.notify(title, message, tags=tags or ["warning"], logger=log)
        self._update_request(estado=REQUEST_ESTADO.get(state, state), referencia=ref,
                             mensagem=common.sanitize(message)[:400], forcar="NAO")
        return 0 if state in ("CONFIRMED", "SOLD_OUT") else 2

    def run(self) -> int:
        if not self.lock.acquire():
            log.info("%s: já há outra tentativa em curso — a sair.", self.label)
            return 0
        try:
            return self._run()
        except Exception as e:  # noqa: BLE001 — rede de segurança: nada falha calado
            log.error("Erro inesperado no pedido: %s\n%s", e, traceback.format_exc())
            notify_once(f"pedido-unexpected-{self.leg.lock_key}-{type(e).__name__}",
                        f"Erro inesperado no pedido — {self.label}", f"{type(e).__name__}: {e}.",
                        cooldown_s=1800, logger=log)
            self.slog("ERRO", "EXCECAO", err=f"{type(e).__name__}: {e}")
            self._update_request(estado="FALHOU", mensagem=common.sanitize(f"{type(e).__name__}: {e}")[:400], forcar="NAO")
            return 1
        finally:
            self.flush_tentativas()
            self.lock.release()

    def _run(self) -> int:
        self.lock.update(state="A_TENTAR", leg=self.leg.key, train=self.leg.train)
        self._update_request(estado="A_TENTAR", forcar="NAO")
        if already_bought(self._sheets(), self.leg):
            self.lock.update(state="CONFIRMED", note="já constava em Bilhetes")
            self.notify(f"Já comprado — {self.label}",
                        "Este bilhete já consta na aba Bilhetes; não comprei outra vez.",
                        tags=["white_check_mark"], logger=log)
            self._update_request(estado="CONFIRMADO", forcar="NAO")
            return 0

        try:
            tokens = self.login_fn()
            self.cp = self.cp_factory(tokens["access_token"])
            common.save_tokens(tokens)
            log.info("Login na CP bem-sucedido (pedido).")
        except Exception as e:  # noqa: BLE001
            return self.terminate("FAILED", f"Login na CP falhou — {self.label}",
                                  f"{type(e).__name__}: {e}.", "ERRO")

        sections = self.search_trip()
        if sections is None:
            return 2   # search_trip() já terminou (sem serviço em cache para tentar às cegas)

        outcome, resp = self.fire_sale(sections)
        if outcome != "ok":
            return 0 if outcome == "sold_out" else 2
        self.improve_seat(resp.body["saleID"])       # lugar ao corredor (a venda já segura o lugar: não é uma corrida)
        return self.complete_sale(resp.body["saleID"])

    def search_trip(self) -> list | None:
        cache_path = common._state_file("trains.json")
        trains = common._read_json(cache_path, {})
        ckey = f"{self.leg.train}|{self.leg.origin}|{self.leg.destination}"
        try:
            journeys = self.cp.search_journeys(self.origin_code, self.dest_code, self.leg.date.isoformat())
            trip = pick_trip(journeys, train_number=self.leg.train, require_saleable=False)
            sections = trip_sections(trip, self.origin_code, self.dest_code)
            trains[ckey] = sections
            common._write_json_atomic(cache_path, trains)
        except (CPError, RuntimeError, KeyError, TypeError) as e:
            log.error("Pesquisa falhou (pedido): %s: %s", type(e).__name__, e)
            sections = trains.get(ckey)
            if sections is None:
                self.terminate("FAILED", f"Não encontrei o comboio — {self.label}",
                               f"{e}. Sem dados do serviço não consigo comprar; verifica nº e data.", "ERRO")
                return None
        self.lock.update(sections=sections)
        return sections

    def fire_sale(self, sections: list) -> tuple[str, Any]:
        """UM disparo, com no máximo 1 repetição — só para um erro técnico (nunca esgotado/
        recusa: aí a tentativa acaba já, sem rajada nem espera)."""
        target = self.clock()
        for attempt in (1, 2):
            try:
                resp = self.cp.create_sale_request(self.leg.date.isoformat(), sections)
            except CPError as e:
                if e.kind == "not_sent" and attempt == 1:
                    log.warning("POST /sale (pedido) não chegou a sair (%s) — 1 repetição", e)
                    self.sleep(0.5)
                    continue
                if e.kind == "not_sent":
                    self.terminate("FAILED", f"Compra falhou — {self.label}", f"Sem ligação à CP ({e}).", "ERRO")
                    return "failed", None
                self.terminate("AMBIGUOUS", f"Estado AMBÍGUO — {self.label}",
                               "O pedido de compra pode ter chegado à CP mas perdi a resposta. NÃO repeti. "
                               "Confirma na App CP se o bilhete existe.", "ERRO", tags=["question"])
                return "ambiguous", None

            kind, detail = classify_sale_response(resp)
            timing = Buyer._timing_txt(resp, target)
            self._tent("venda", resp, kind, detalhe=detail)
            log.info("POST /sale (pedido) #%d -> HTTP %s [%s] %s", attempt, resp.status, kind, timing)
            if kind == "ok":
                sale_id = resp.body["saleID"]
                seats = collect_seats(resp.body)
                self.lock.update(seats=seats, state="SALE_CREATED", sale_id=sale_id, timing=timing)
                self.slog("COMPRA", "SALE_CREATED", status=resp.status, ref=str(sale_id), err=timing)
                return "ok", resp
            if kind == "transient" and attempt == 1:
                self.sleep(0.5)
                continue
            if kind == "sold_out":
                self.terminate("SOLD_OUT", f"Esgotado — {self.label}", f"Não há lugares. {detail}", "COMPRA",
                               tags=["no_entry"], status=resp.status)
                return "sold_out", None
            self.terminate("FAILED", f"Compra falhou — {self.label}", f"{detail}. Resposta: {resp.text[:300]}",
                           "ERRO", status=resp.status)
            return "failed", None
        return "failed", None  # inalcançável (o loop cobre os 2 casos), só para o type-checker

    def _step_once(self, name: str, fn: Callable[[int], Any], sale_id: int) -> Any:
        for attempt in (1, 2):
            try:
                return fn(sale_id)
            except CPError as e:
                status = e.response.status if e.response is not None else None
                if status in (401, 403) and attempt == 1:
                    try:
                        tokens = refresh_tokens(common.load_tokens()["refresh_token"])
                        self.cp.access_token = tokens["access_token"]
                        common.save_tokens(tokens)
                    except Exception:  # noqa: BLE001 — se o refresh falhar, a repetição abaixo falha na mesma
                        pass
                    continue
                retryable = e.kind in ("not_sent", "ambiguous") or (status is not None and status >= 500)
                if retryable and attempt == 1:
                    self.sleep(1)
                    continue
                if name == "DISCOUNT_OK" and e.response is not None and isinstance(e.response.body, dict) \
                        and e.response.body.get("error") == "SIV:DIS:I:302":
                    # antes de T (24 h antes da partida na 1.ª estação) a CP recusa o desconto do passe: não há nada a concluir
                    try:
                        self.cp.cancel_sale(sale_id)
                    except Exception:  # noqa: BLE001 — melhor esforço
                        pass
                    self.terminate("FAILED", f"O desconto do passe ainda não abriu — {self.label}",
                                   f"O desconto só é aceite 24 h antes da partida na 1.ª estação. Nada foi comprado e libertei o "
                                   f"lugar (venda {sale_id}). Tenta outra vez a partir dessa hora (ou deixa a Config tratar: retém "
                                   "o lugar 10 min antes).", "ERRO")
                    return None
                if name == "CONFIRMED" and e.kind == "ambiguous":
                    self.terminate("AMBIGUOUS", f"Confirmação incerta — {self.label}",
                                   f"A venda {sale_id} existe mas não sei se foi confirmada. "
                                   "Confirma na App CP antes de repetir.", "ERRO", tags=["question"])
                    return None
                self.terminate("FAILED", f"Venda por concluir — {self.label}",
                               f"Falhou no passo {name} da venda {sale_id}: {e}. A venda pode expirar ao "
                               "fim de 15 min: conclui na App CP se ainda a vires.", "ERRO")
                return None
        return None

    def complete_sale(self, sale_id: int) -> int:
        methods = {"PASSENGERS_OK": self.cp.set_passengers, "CLIENT_OK": self.cp.set_client,
                   "FISCAL_OK": self.cp.set_fiscal, "DISCOUNT_OK": self.cp.apply_green_pass,
                   "CONFIRMED": self.cp.confirm}
        resp = None
        for name in ("PASSENGERS_OK", "CLIENT_OK", "FISCAL_OK", "DISCOUNT_OK", "CONFIRMED"):
            resp = self._step_once(name, methods[name], sale_id)
            if resp is None:
                return 2   # _step_once já terminou
            if resp.messages:
                log.warning("Mensagens da CP em %s (pedido): %s", name, " | ".join(resp.messages))
            if name == "DISCOUNT_OK":
                total = to_amount(find_key(resp.body, "totalAmount"))
                if total is not None and total != 0.0:
                    self.terminate("FAILED", f"Desconto do passe não aplicado — {self.label}",
                                   f"Total da venda {sale_id} ficou {total}€ em vez de 0€. Não confirmei. "
                                   "Verifica o passe (validade/número).", "ERRO")
                    return 2
            if name == "CONFIRMED":
                status = resp.body.get("status") if isinstance(resp.body, dict) else None
                status_code = status.get("code") if isinstance(status, dict) else None
                if status_code != "CONFIRMED":
                    self.terminate("FAILED", f"Venda não confirmada — {self.label}",
                                   f"Estado devolvido pela CP: {status_code!r}.", "ERRO", status=resp.status)
                    return 2
            self.lock.update(state=name)
        return self.on_confirmed(resp)

    def find_seats(self, body: Any) -> list[dict]:
        st = self.lock.state
        seats = merge_seats(list(st.get("seats") or []), collect_seats(body))
        if not seats and st.get("sale_id"):
            try:
                seats = collect_seats(self.cp.get_sale(st["sale_id"]).body)
            except Exception as e:  # noqa: BLE001 — último recurso, nunca impede a confirmação
                log.warning("Não consegui ler a venda %s para obter o lugar: %s", st["sale_id"], type(e).__name__)
        if not seats:
            c = find_key(body, "carriageNumber") or st.get("carriage")
            s_ = find_key(body, "seatNumber") or st.get("seat")
            if c or s_:
                seats = [{"carriage": c, "seat": s_, "train": None}]
        return seats

    def on_confirmed(self, resp: Any) -> int:
        body = resp.body if resp is not None else {}
        ref = str(body.get("reference", "")) if isinstance(body, dict) else ""
        seats = self.find_seats(body)
        complete = [x for x in seats if x["carriage"] not in (None, "") and x["seat"] not in (None, "")]
        carriages = [x["carriage"] for x in seats if x["carriage"] not in (None, "")]
        pieces = [x["seat"] for x in seats if x["seat"] not in (None, "")]
        carriage = carriages[0] if len(carriages) == 1 else (" / ".join(str(c) for c in carriages) or None)
        seat = pieces[0] if len(pieces) == 1 else (" / ".join(str(p) for p in pieces) or None)
        self.lock.update(reference=ref, carriage=carriage, seat=seat, seats=seats)
        leg = self.leg
        pretty = lambda k: k.replace("_", " ").title()  # noqa: E731
        boarding = leg.board or leg.hhmm
        self.sheet("append_ticket", leg.date.isoformat(), leg.train, pretty(leg.origin),
                   pretty(leg.destination), boarding, carriage or "", seat or "", ref)
        have_seat = bool(complete)
        seat_txt = (seat_phrase(complete) if have_seat else
                    f"carruagem {carriage}" if carriage else f"lugar {seat}" if seat else
                    "carruagem e lugar não devolvidos pela CP — vê na App CP")
        route = f"Comboio {leg.train} · {pretty(leg.origin)} → {pretty(leg.destination)}"
        remind_ts = leg.departure.timestamp() - 30 * 60
        remind_at = datetime.fromtimestamp(remind_ts, TZ)
        reminder_ok = False
        if remind_ts > time.time() + 120:
            title = f"Partida às {boarding} · {seat_txt}" if have_seat else f"Partida às {boarding} (daqui a 30 min)"
            reminder_ok = self.notify(title, f"{route}. {seat_txt[0].upper() + seat_txt[1:]}.",
                                      tags=["train"], at=remind_at, logger=log)
        self.lock.update(reminder_scheduled=reminder_ok, seat_known=have_seat)
        extra = "" if reminder_ok else " (lembrete de partida não agendado)"
        nota, aviso = self.seat_note(carriage, seat)
        return self.terminate("CONFIRMED", f"Bilhete comprado — {self.label}",
                              f"{pretty(leg.origin)} → {pretty(leg.destination)} às {boarding} · {seat_txt}{nota} · "
                              f"ref. {ref}{extra}{aviso}", "COMPRA", tags=["white_check_mark"], ref=ref)


def load_pedido_leg(leg_name: str) -> Leg | None:
    row = int(leg_name.removeprefix("pedido"))
    rows = common.get_store().read_requests()
    legs, _ = common.parse_request_rows(rows, common.now_local().date())
    return next((l for l in legs if l.row == row), None)


# ---------------------------------------------------------------------------

def load_leg(d: str, leg_name: str) -> Leg | None:
    if leg_name.startswith("pedido"):
        return load_pedido_leg(leg_name)
    today = common.now_local().date()
    target = datetime.strptime(d, "%Y-%m-%d").date()
    for source in ("cache", "sheet"):
        snap = common.load_config_cache() if source == "cache" else None
        if source == "sheet":
            try:
                snap = common.get_store().read_config()
                common.save_config_cache(snap)
            except Exception as e:  # noqa: BLE001
                log.error("Não consegui ler a Sheet: %s", type(e).__name__)
                snap = None
        if not snap:
            continue
        legs, _ = common.parse_config_rows(snap["weekly"], min(today, target))
        for l in legs:
            if l.date == target and l.leg == leg_name:
                return timetable.apply_anchor(l)     # disparo à partida do comboio na 1.ª estação
    return None


def search_only(leg: Leg, cp_factory=CPClient, out=print) -> int:
    """`--search-only` (PLANO_FINAL 3.10.7): corre a pesquisa e a escolha do comboio, mostra o
    que se compraria, e pára. NUNCA cria uma venda, não usa lock, estado, Sheet nem ntfy, e
    dispensa login (o `journeys` não o exige). Serve para validar uma perna real sem risco."""
    origin, dest = station_code(leg.origin) or "", station_code(leg.destination) or ""
    out(f"Perna {leg.key}: comboio {leg.train}, partida {leg.hhmm}, {leg.origin} -> {leg.destination}")
    out(f"  disparo (T-24h): {leg.fire:%a %d/%m %H:%M:%S %Z}; o processo arrancaria "
        f"{float(cfg('launch_lead_minutes', 6)):.0f} min antes")
    if leg.anchor:
        out(f"  disparo à partida do comboio na 1.ª estação ({leg.anchor}); embarque em {leg.origin} às {leg.board or leg.hhmm}")
    else:
        out(f"  sem a hora da 1.ª estação: disparo pela hora da Config ({leg.hhmm})")
    try:
        journeys = cp_factory("").search_journeys(origin, dest, leg.date.isoformat())
        trip = pick_trip(journeys, train_number=leg.train, require_saleable=False)
        sections = trip_sections(trip, origin, dest)
    except (CPError, RuntimeError, KeyError, TypeError) as e:
        out(f"  FALHA na pesquisa: {common.sanitize(e)}")
        return 2
    dep = str(trip.get("departureTime", ""))[:5]
    out(f"  a CP tem a viagem: parte {dep}, chega {str(trip.get('arrivalTime', ''))[:5]}, "
        f"vendável online: {trip.get('saleableOnline')} (não indica a janela de venda)")
    for s in sections:
        out(f"  secção: comboio {s['train']} {s['dep']} -> {s['arr']} ({s['designation']})")
    ok = leg.hhmm in (dep, leg.anchor or dep)              # vale a hora da 1.ª estação ou a de embarque
    out("  hora da Config " + ("bate certo com a CP." if ok
                              else f"NÃO bate certo: Config {leg.hhmm}, CP {dep} no embarque (a compra é pelo nº do comboio)."))
    out("Nenhuma venda foi criada.")
    return 0


def _leg_arg(v: str) -> str:
    """'vN' (linha N da Config, 3.10.3) ou 'pedidoN' (linha N da aba Pedidos, 3.2.1)."""
    if re.fullmatch(r"v\d+", v) or re.fullmatch(r"pedido\d+", v):
        return v
    raise argparse.ArgumentTypeError(f"leg inválida: {v!r} (vN ou pedidoN)")


def main() -> int:
    ap = argparse.ArgumentParser(description="Compra de uma viagem (lançado pelo Scheduler ou pela fila de Pedidos)")
    ap.add_argument("--date", required=True, help="data da viagem YYYY-MM-DD")
    ap.add_argument("--leg", required=True, type=_leg_arg)
    ap.add_argument("--search-only", action="store_true",
                    help="só pesquisa e mostra o que compraria; nunca cria uma venda")
    args = ap.parse_args()

    leg = load_leg(args.date, args.leg)
    if leg is None:
        if args.search_only:
            print("Esta perna não consta da Config (ou não é válida).")
            return 1
        notify_once(f"hotbuy-no-leg-{args.date}-{args.leg}", f"Compra sem configuração — {args.date} {args.leg}",
                    "O processo de compra arrancou mas esta perna já não consta da Config (foi desativada "
                    "ou alterada?). Não comprei nada.", cooldown_s=3600, logger=log)
        return 1
    if args.search_only:
        return search_only(leg)
    if leg.is_request:
        return PedidoAttempt(leg, PurchaseLock(leg.lock_key)).run()
    return Buyer(leg, PurchaseLock(leg.lock_key)).run()


if __name__ == "__main__":
    sys.exit(main())
