"""Previsão do tempo (ADR-092): Open-Meteo simulada."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, config
from pulse.main import create_app
from pulse.services.tempo import PADRAO, Tempo, TempoIndisponivel, estado_do_ceu

AGORA = datetime(2026, 10, 2, 15, 20)
EMAIL = "bruno@example.com"


def bruto(temp=17.2, codigo=3):
    horas = [f"2026-10-02T{h:02d}:00" for h in range(0, 24)] + [f"2026-10-03T{h:02d}:00" for h in range(0, 24)]
    return {"current": {"temperature_2m": temp, "weather_code": codigo, "is_day": 1, "wind_speed_10m": 14.4},
            "hourly": {"time": horas, "temperature_2m": [10 + i * 0.1 for i in range(len(horas))], "precipitation_probability": [i % 100 for i in range(len(horas))],
                       "weather_code": [61] * len(horas), "is_day": [1] * len(horas)},
            "daily": {"time": [f"2026-10-0{d}" for d in range(2, 8)], "weather_code": [3, 61, 0, 80, 95, 71], "temperature_2m_max": [20, 19, 21, 18, 17, 3.4],
                      "temperature_2m_min": [12, 11, 10, 9, 8, -1], "precipitation_probability_max": [10, 80, 0, 60, 90, 40],
                      "sunrise": [f"2026-10-0{d}T07:41" for d in range(2, 8)], "sunset": [f"2026-10-0{d}T19:12" for d in range(2, 8)]}}


class Falso:
    def __init__(self, resposta=None, falha=False):
        self.resposta, self.falha, self.urls = resposta or bruto(), falha, []

    def __call__(self, url):
        self.urls.append(url)
        if self.falha:
            raise TempoIndisponivel("em baixo")
        return self.resposta


def test_formata_agora_hoje_horas_e_dias_em_pt():
    r = Tempo(Falso()).previsao(40.64123, -8.65311, AGORA)
    assert r["localizacao"] == "dispositivo"
    assert (r["agora"]["temp"], r["agora"]["icone"], r["agora"]["descricao"], r["agora"]["vento"]) == (17.2, "nublado", "Nublado", 14.0)
    assert (r["hoje"]["max"], r["hoje"]["min"], r["hoje"]["chuva"], r["hoje"]["nascer"], r["hoje"]["poer"]) == (20.0, 12.0, 10, "07:41", "19:12")
    assert len(r["dias"]) == 6 and r["dias"][0]["diaSemana"] == "sexta" and r["dias"][1]["icone"] == "chuva" and r["dias"][5]["icone"] == "neve"
    assert len(r["horas"]) == 24 and r["horas"][0]["hora"] == "15:00" and r["horas"][0]["dia"] == "2026-10-02" and r["horas"][-1]["dia"] == "2026-10-03"   # as 24 h a partir da hora atual


def test_sem_coordenadas_validas_usa_aveiro_e_diz_que_e_por_omissao():
    f = Falso()
    r = Tempo(f).previsao(None, None, AGORA)
    assert r["localizacao"] == "omissao" and f"latitude={PADRAO[0]}" in f.urls[0] and f"longitude={PADRAO[1]}" in f.urls[0]
    assert Tempo(Falso()).previsao(123.0, 10.0, AGORA)["localizacao"] == "omissao"          # latitude impossível


def test_coordenadas_arredondadas_partilham_a_cache_30_min_e_a_velha_serve_se_a_fonte_falhar():
    t = [1000.0]
    f = Falso()
    tempo = Tempo(f, agora=lambda: t[0])
    tempo.previsao(40.6401, -8.6502, AGORA); tempo.previsao(40.6399, -8.6498, AGORA)     # as duas arredondam a 40.64 / -8.65
    assert len(f.urls) == 1 and "latitude=40.64" in f.urls[0]
    t[0] += 3600                                                                          # passada a cache de 30 min, a fonte está em baixo: serve a velha
    f.falha = True
    assert tempo.previsao(40.64, -8.65, AGORA)["agora"]["temp"] == 17.2
    t[0] += 7 * 3600                                                                      # velha de mais: erro
    with pytest.raises(TempoIndisponivel):
        tempo.previsao(40.64, -8.65, AGORA)


def test_resposta_inesperada_e_indisponivel():
    with pytest.raises(TempoIndisponivel):
        Tempo(Falso(resposta={"x": 1})).previsao(40.64, -8.65, AGORA)


@pytest.mark.parametrize("codigo,dia,icone", [(0, True, "sol"), (0, False, "lua"), (2, True, "pouco_nublado"), (45, True, "nevoeiro"), (63, True, "chuva"),
                                              (81, True, "aguaceiros"), (73, True, "neve"), (95, True, "trovoada"), (None, True, "nublado")])
def test_icone_do_ceu(codigo, dia, icone):
    assert estado_do_ceu(codigo, dia)[0] == icone


@pytest.fixture
def cliente(tmp_path):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-t1.db"), "PULSE_SERVICE_KEY": "k" * 40, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s, tempo=Tempo(Falso())); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        yield c


def test_api_exige_sessao_e_devolve_a_previsao(cliente):
    r = cliente.get("/api/v1/weather?lat=40.64&lon=-8.65")
    assert r.status_code == 200 and r.json()["agora"]["icone"] == "nublado" and r.json()["localizacao"] == "dispositivo"
    assert cliente.get("/api/v1/weather").json()["localizacao"] == "omissao"
    assert cliente.get("/api/v1/weather?lat=abc").status_code in (400, 422)
    cliente.cookies.clear()
    assert cliente.get("/api/v1/weather").status_code == 401


def test_api_fonte_em_baixo_e_503_em_pt(tmp_path):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-t2.db"), "PULSE_SERVICE_KEY": "k" * 40, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s, tempo=Tempo(Falso(falha=True))); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db(); accounts.criar_utilizador(k, EMAIL, "1234qweR", must_change=False); k.close()
        c.post("/api/v1/auth/login", json={"email": EMAIL, "password": "1234qweR"})
        r = c.get("/api/v1/weather")
        assert r.status_code == 503 and "previsão do tempo" in r.text
