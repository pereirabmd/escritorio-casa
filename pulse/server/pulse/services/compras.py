"""Compras (ADR-047): catálogo, listas e itens. Único módulo cujos dados são do próprio Pulse (`pulse.db`).

Regras que a interface e a IA partilham (por isso vivem aqui e não nos ecrãs):
- há a lista **«Casa»** (partilhada por todas as contas) e listas **pessoais** (só o dono as vê) ou outras partilhadas;
- um produto aparece **uma só vez** por lista; tocar num produto já comprado reativa-o (nunca duplica);
- a quantidade é opcional e só se define nos detalhes do item: adicionar nunca a incrementa;
- as operações **definem** estados (`comprado = verdadeiro`, `quantidade = 3`) em vez de os alternar, para se poderem repetir sem efeito
  (fila offline do Android) e ser idempotentes por `cid`.
"""

from __future__ import annotations

import sqlite3
import statistics
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from pulse import compras_catalogo as cat
from pulse.accounts import ContaErro

MAX_LISTAS_POR_TIPO = 10
NOTA_MAX = 80


@contextmanager
def _tx(conn: sqlite3.Connection):
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def _agora(agora: int | None) -> int:
    return agora if agora is not None else int(time.time())


def _nao_encontrado(o_que: str) -> ContaErro:
    return ContaErro(404, "nao_encontrado", f"{o_que} inexistente")


# --- catálogo de série ---------------------------------------------------------------------------------------------------------

def sincronizar_catalogo(conn: sqlite3.Connection, agora: int | None = None) -> int:
    """Insere os produtos de série que faltam e atualiza nome, categoria e ícone dos existentes. Devolve quantos entraram.
    Um produto próprio com o mesmo nome fica como está e o de série é saltado (o utilizador ganha)."""
    t, novos = _agora(agora), 0
    with _tx(conn):
        for p in cat.produtos():
            ja = conn.execute("SELECT id FROM shop_products WHERE slug = ?", (p["slug"],)).fetchone()
            try:
                if ja:
                    conn.execute("UPDATE shop_products SET nome = ?, categoria = ?, icone = ?, builtin = 1 WHERE id = ?", (p["nome"], p["categoria"], p["icone"], ja["id"]))
                else:
                    conn.execute("INSERT INTO shop_products (slug, nome, categoria, icone, builtin, criado) VALUES (?,?,?,?,1,?)", (p["slug"], p["nome"], p["categoria"], p["icone"], t))
                    novos += 1
            except sqlite3.IntegrityError:
                continue            # já existe um produto (próprio) com este nome
    return novos


# --- listas --------------------------------------------------------------------------------------------------------------------

def _lista_visivel(conn: sqlite3.Connection, lista: int, uid: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM shop_lists WHERE id = ? AND (tipo = 'partilhada' OR dono_id = ?)", (lista, uid)).fetchone()
    if r is None:
        raise _nao_encontrado("lista")       # a lista de outra pessoa não se distingue de uma que não existe
    return r


def _listas(conn: sqlite3.Connection, uid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT l.*, COALESCE(SUM(i.estado = 'pendente'), 0) AS pendentes, COUNT(i.id) AS total FROM shop_lists l LEFT JOIN shop_items i ON i.list_id = l.id "
        "WHERE l.tipo = 'partilhada' OR l.dono_id = ? GROUP BY l.id ORDER BY l.padrao DESC, l.tipo, l.id", (uid,)).fetchall()
    return [{"id": r["id"], "nome": r["nome"], "tipo": r["tipo"], "padrao": bool(r["padrao"]), "pendentes": r["pendentes"], "total": r["total"]} for r in rows]


def _nome_lista(nome: str) -> str:
    nome = " ".join(nome.split())
    if not 1 <= len(nome) <= 60:
        raise ContaErro(400, "nome_invalido", "o nome da lista tem de ter entre 1 e 60 caracteres")
    return nome


def lista_criar(conn, uid: int, nome: str, tipo: str, agora: int | None = None) -> dict:
    nome = _nome_lista(nome)
    if tipo not in ("partilhada", "pessoal"):
        raise ContaErro(400, "tipo_invalido", "tipo tem de ser partilhada ou pessoal")
    with _tx(conn):
        dono = uid if tipo == "pessoal" else None
        n = conn.execute("SELECT COUNT(*) FROM shop_lists WHERE tipo = ? AND padrao = 0 AND dono_id IS ?", (tipo, dono)).fetchone()[0]
        if n >= MAX_LISTAS_POR_TIPO:
            raise ContaErro(400, "demasiadas_listas", f"no máximo {MAX_LISTAS_POR_TIPO} listas {'pessoais' if tipo == 'pessoal' else 'partilhadas'}")
        cur = conn.execute("INSERT INTO shop_lists (nome, tipo, dono_id, criado) VALUES (?,?,?,?)", (nome, tipo, dono, _agora(agora)))
    return {"id": cur.lastrowid, "nome": nome, "tipo": tipo}


def _lista_gerivel(conn, lista: int, uid: int) -> sqlite3.Row:
    r = _lista_visivel(conn, lista, uid)
    if r["padrao"]:
        raise ContaErro(403, "lista_padrao", "a lista «Casa» não se pode renomear nem apagar")
    return r


def lista_editar(conn, uid: int, lista: int, nome: str) -> dict:
    r = _lista_gerivel(conn, lista, uid)
    nome = _nome_lista(nome)
    conn.execute("UPDATE shop_lists SET nome = ? WHERE id = ?", (nome, lista))
    return {"id": lista, "nome": nome, "tipo": r["tipo"]}


def lista_apagar(conn, uid: int, lista: int) -> dict:
    r = _lista_gerivel(conn, lista, uid)
    itens = conn.execute("SELECT COUNT(*) FROM shop_items WHERE list_id = ?", (lista,)).fetchone()[0]
    conn.execute("DELETE FROM shop_lists WHERE id = ?", (lista,))
    return {"id": lista, "nome": r["nome"], "itens": itens}


# --- produtos ------------------------------------------------------------------------------------------------------------------

def _produto(conn, produto: int) -> sqlite3.Row:
    r = conn.execute("SELECT * FROM shop_products WHERE id = ?", (produto,)).fetchone()
    if r is None:
        raise _nao_encontrado("produto")
    return r


def _validar_produto(nome: str, categoria: str, icone: str | None) -> tuple[str, str, str]:
    nome = " ".join(nome.split())
    if not 1 <= len(nome) <= 80:
        raise ContaErro(400, "nome_invalido", "o nome do produto tem de ter entre 1 e 80 caracteres")
    if categoria not in cat.CATEGORIA_IDS:
        raise ContaErro(400, "categoria_invalida", "categoria desconhecida")
    if icone is not None and icone not in cat.ICONES:
        raise ContaErro(400, "icone_invalido", "ícone desconhecido")
    return nome, categoria, icone or cat.ICONE_DA_CATEGORIA[categoria]


def produto_criar(conn, uid: int, nome: str, categoria: str, icone: str | None = None, agora: int | None = None) -> dict:
    nome, categoria, icone = _validar_produto(nome, categoria, icone)
    try:
        cur = conn.execute("INSERT INTO shop_products (nome, categoria, icone, builtin, criado_por, criado) VALUES (?,?,?,0,?,?)", (nome, categoria, icone, uid, _agora(agora)))
    except sqlite3.IntegrityError:
        raise ContaErro(409, "ja_existe", "já existe um produto com esse nome") from None
    return {"id": cur.lastrowid, "nome": nome, "categoria": categoria, "icone": icone}


def _produto_proprio(conn, uid: int, produto: int, admin: bool) -> sqlite3.Row:
    r = _produto(conn, produto)
    if r["builtin"]:
        raise ContaErro(403, "produto_de_serie", "os produtos de série só se podem esconder ou marcar como favoritos")
    if r["criado_por"] != uid and not admin:
        raise ContaErro(403, "sem_permissao", "só quem criou o produto (ou o administrador) o pode alterar")
    return r


def produto_editar(conn, uid: int, admin: bool, produto: int, nome: str | None, categoria: str | None, icone: str | None) -> dict:
    r = _produto_proprio(conn, uid, produto, admin)
    n, c, i = _validar_produto(nome if nome is not None else r["nome"], categoria if categoria is not None else r["categoria"], icone if icone is not None else r["icone"])
    try:
        conn.execute("UPDATE shop_products SET nome = ?, categoria = ?, icone = ? WHERE id = ?", (n, c, i, produto))
    except sqlite3.IntegrityError:
        raise ContaErro(409, "ja_existe", "já existe um produto com esse nome") from None
    return {"id": produto, "nome": n, "categoria": c, "icone": i}


def produto_apagar(conn, uid: int, admin: bool, produto: int) -> dict:
    r = _produto_proprio(conn, uid, produto, admin)
    itens = conn.execute("SELECT COUNT(*) FROM shop_items WHERE product_id = ?", (produto,)).fetchone()[0]
    conn.execute("DELETE FROM shop_products WHERE id = ?", (produto,))
    return {"id": produto, "nome": r["nome"], "categoria": r["categoria"], "icone": r["icone"], "itens": itens}


def _marcar(conn, uid: int, produto: int, campo: str, valor: bool) -> dict:
    _produto(conn, produto)
    conn.execute("INSERT INTO shop_user_products (user_id, product_id) VALUES (?,?) ON CONFLICT DO NOTHING", (uid, produto))
    conn.execute(f"UPDATE shop_user_products SET {campo} = ? WHERE user_id = ? AND product_id = ?", (int(valor), uid, produto))
    conn.execute("DELETE FROM shop_user_products WHERE user_id = ? AND product_id = ? AND favorito = 0 AND oculto = 0 AND sem_sugestoes = 0", (uid, produto))
    return {"produto": produto, campo: valor}


def favorito(conn, uid: int, produto: int, valor: bool) -> dict:
    return _marcar(conn, uid, produto, "favorito", valor)


def sugestao_ignorar(conn, uid: int, produto: int, valor: bool) -> dict:
    """«Não sugerir este produto» (por conta). Não muda o catálogo nem as listas."""
    return _marcar(conn, uid, produto, "sem_sugestoes", valor)


def categoria_ocultar(conn, uid: int, categoria: str, valor: bool) -> dict:
    """Esconde (ou volta a mostrar) uma categoria inteira do catálogo desta conta. O que já está numa lista continua a ver-se lá."""
    if categoria not in cat.CATEGORIA_IDS:
        raise ContaErro(400, "categoria_invalida", "categoria desconhecida")
    if valor:
        conn.execute("INSERT INTO shop_user_categories (user_id, categoria) VALUES (?,?) ON CONFLICT DO NOTHING", (uid, categoria))
    else:
        conn.execute("DELETE FROM shop_user_categories WHERE user_id = ? AND categoria = ?", (uid, categoria))
    return {"categoria": categoria, "oculta": valor}


def ocultar(conn, uid: int, produto: int, valor: bool) -> dict:
    return _marcar(conn, uid, produto, "oculto", valor)


# --- itens ---------------------------------------------------------------------------------------------------------------------

def _item_json(conn, item: int) -> dict:
    r = conn.execute("SELECT i.*, p.nome, p.categoria, p.icone, u.nome AS por_nome, u.email AS por_email FROM shop_items i JOIN shop_products p ON p.id = i.product_id "
                     "LEFT JOIN pulse_users u ON u.id = i.adicionado_por WHERE i.id = ?", (item,)).fetchone()
    return _linha(r)


def _linha(r) -> dict:
    return {"id": r["id"], "lista": r["list_id"], "produto": r["product_id"], "nome": r["nome"], "categoria": r["categoria"], "icone": r["icone"],
            "quantidade": r["quantidade"], "nota": r["nota"], "estado": r["estado"], "adicionadoPor": (r["por_nome"] or r["por_email"] or "") if r["adicionado_por"] else "",
            "compradoEm": r["comprado_em"]}


def _item_visivel(conn, uid: int, item: int) -> sqlite3.Row:
    r = conn.execute("SELECT i.* FROM shop_items i JOIN shop_lists l ON l.id = i.list_id WHERE i.id = ? AND (l.tipo = 'partilhada' OR l.dono_id = ?)", (item, uid)).fetchone()
    if r is None:
        raise _nao_encontrado("item")
    return r


def adicionar(conn, uid: int, lista: int, produto: int | None = None, nome: str | None = None, categoria: str | None = None, icone: str | None = None,
              cid: str | None = None, agora: int | None = None) -> dict:
    """Põe um produto na lista. Por `produto` (id) ou por `nome` (usa o produto com esse nome, ou cria um próprio). Devolve o item e
    `novo` (falso se já estava por comprar). Um item comprado volta a ficar por comprar, sem quantidade nem nota."""
    if (produto is None) == (nome is None):
        raise ContaErro(400, "parametros_invalidos", "indica o produto ou o nome")
    t = _agora(agora)
    with _tx(conn):
        _lista_visivel(conn, lista, uid)
        if cid:
            ja = conn.execute("SELECT id FROM shop_items WHERE cid = ?", (cid,)).fetchone()
            if ja:
                return {**_item_json(conn, ja["id"]), "novo": False}
        if produto is None:
            existente = conn.execute("SELECT id FROM shop_products WHERE nome = ?", (" ".join(nome.split()),)).fetchone()
            produto = existente["id"] if existente else produto_criar(conn, uid, nome, categoria or "outros", icone, t)["id"]
        else:
            _produto(conn, produto)
        atual = conn.execute("SELECT id, estado FROM shop_items WHERE list_id = ? AND product_id = ?", (lista, produto)).fetchone()
        if atual is None:
            cur = conn.execute("INSERT INTO shop_items (list_id, product_id, adicionado_por, criado, cid) VALUES (?,?,?,?,?)", (lista, produto, uid, t, cid))
            return {**_item_json(conn, cur.lastrowid), "novo": True}
        if atual["estado"] == "comprado":
            conn.execute("UPDATE shop_items SET estado = 'pendente', comprado_em = NULL, comprado_por = NULL, quantidade = NULL, nota = '', adicionado_por = ?, criado = ? WHERE id = ?", (uid, t, atual["id"]))
            return {**_item_json(conn, atual["id"]), "novo": True}
        return {**_item_json(conn, atual["id"]), "novo": False}


def remover(conn, uid: int, item: int) -> dict:
    """Tira o item da lista e devolve o que ele era (para o «Desfazer» o repor com `restaurar`)."""
    _item_visivel(conn, uid, item)
    antes = _item_json(conn, item)
    conn.execute("DELETE FROM shop_items WHERE id = ?", (item,))
    return antes


def _dia(agora: int | None, dia: str | None) -> str:
    return dia or datetime.fromtimestamp(_agora(agora)).date().isoformat()


def comprado(conn, uid: int, item: int, valor: bool, agora: int | None = None, dia: str | None = None) -> dict:
    """Marca (ou desmarca) como comprado. Ao passar de «por comprar» a «comprado» fica um registo no histórico (uma vez por dia,
    por produto e âmbito) que alimenta as sugestões; desmarcar retira o registo de hoje, para um toque enganado não contar."""
    it = _item_visivel(conn, uid, item)
    lista = conn.execute("SELECT tipo, dono_id FROM shop_lists WHERE id = ?", (it["list_id"],)).fetchone()
    escopo = "partilhada" if lista["tipo"] == "partilhada" else f"pessoal:{lista['dono_id']}"
    d = _dia(agora, dia)
    if valor:
        conn.execute("UPDATE shop_items SET estado = 'comprado', comprado_em = COALESCE(comprado_em, ?), comprado_por = COALESCE(comprado_por, ?) WHERE id = ?", (_agora(agora), uid, item))
        if it["estado"] != "comprado":
            conn.execute("INSERT INTO shop_history (product_id, escopo, dia, user_id) VALUES (?,?,?,?) ON CONFLICT DO NOTHING", (it["product_id"], escopo, d, uid))
    else:
        conn.execute("UPDATE shop_items SET estado = 'pendente', comprado_em = NULL, comprado_por = NULL WHERE id = ?", (item,))
        if it["estado"] == "comprado":
            conn.execute("DELETE FROM shop_history WHERE product_id = ? AND escopo = ? AND dia = ?", (it["product_id"], escopo, d))
    return _item_json(conn, item)


def detalhes(conn, uid: int, item: int, quantidade: int | None, nota: str) -> dict:
    """Define a quantidade (vazio = sem quantidade) e a nota do item."""
    _item_visivel(conn, uid, item)
    nota = " ".join(nota.split())
    if quantidade is not None and not 1 <= quantidade <= 999:
        raise ContaErro(400, "quantidade_invalida", "a quantidade tem de estar entre 1 e 999")
    if len(nota) > NOTA_MAX:
        raise ContaErro(400, "nota_grande", f"a nota tem no máximo {NOTA_MAX} caracteres")
    conn.execute("UPDATE shop_items SET quantidade = ?, nota = ? WHERE id = ?", (quantidade, nota, item))
    return _item_json(conn, item)


def mover(conn, uid: int, item: int, destino: int) -> dict:
    """Passa o item para outra lista visível. Se o produto já lá estiver, junta-se ao que lá está (fica por comprar se algum estava)."""
    with _tx(conn):
        origem = _item_visivel(conn, uid, item)
        _lista_visivel(conn, destino, uid)
        if origem["list_id"] == destino:
            return _item_json(conn, item)
        ja = conn.execute("SELECT id, estado FROM shop_items WHERE list_id = ? AND product_id = ?", (destino, origem["product_id"])).fetchone()
        if ja is None:
            conn.execute("UPDATE shop_items SET list_id = ? WHERE id = ?", (destino, item))
            return _item_json(conn, item)
        if origem["estado"] == "pendente" and ja["estado"] == "comprado":
            conn.execute("UPDATE shop_items SET estado = 'pendente', comprado_em = NULL, comprado_por = NULL, quantidade = ?, nota = ? WHERE id = ?", (origem["quantidade"], origem["nota"], ja["id"]))
        conn.execute("DELETE FROM shop_items WHERE id = ?", (item,))
        return _item_json(conn, ja["id"])


def limpar_comprados(conn, uid: int, lista: int) -> dict:
    """Apaga os itens comprados e devolve-os (para o «Desfazer» os repor com `restaurar`)."""
    with _tx(conn):
        _lista_visivel(conn, lista, uid)
        rows = conn.execute("SELECT i.*, p.nome, p.categoria, p.icone, NULL AS por_nome, NULL AS por_email FROM shop_items i JOIN shop_products p ON p.id = i.product_id "
                            "WHERE i.list_id = ? AND i.estado = 'comprado'", (lista,)).fetchall()
        conn.execute("DELETE FROM shop_items WHERE list_id = ? AND estado = 'comprado'", (lista,))
    return {"removidos": [_linha(r) for r in rows]}


def restaurar(conn, uid: int, lista: int, itens: list[dict], agora: int | None = None) -> dict:
    """Repõe itens (produto, quantidade, nota, estado) que se tinham tirado — o «Desfazer» de remover e de limpar. Ignora os já presentes."""
    t, repostos = _agora(agora), 0
    with _tx(conn):
        _lista_visivel(conn, lista, uid)
        for it in itens:
            if conn.execute("SELECT 1 FROM shop_products WHERE id = ?", (it["produto"],)).fetchone() is None:
                continue
            cur = conn.execute("INSERT INTO shop_items (list_id, product_id, quantidade, nota, estado, adicionado_por, criado, comprado_em, comprado_por) VALUES (?,?,?,?,?,?,?,?,?) "
                               "ON CONFLICT (list_id, product_id) DO NOTHING",
                               (lista, it["produto"], it.get("quantidade"), it.get("nota", ""), it.get("estado", "pendente"), uid, t,
                                t if it.get("estado") == "comprado" else None, uid if it.get("estado") == "comprado" else None))
            repostos += cur.rowcount
    return {"repostos": repostos}


# --- sugestões -----------------------------------------------------------------------------------------------------------------

JANELA_FREQUENTES_DIAS = 90
JANELA_HISTORICO_DIAS = 180
MIN_COMPRAS_ACABAR = 3               # 3 dias de compra = 2 intervalos para ter um ritmo
INTERVALO_MIN_ACABAR = 5             # abaixo disto (pão, fruta) «a acabar» seria ruído
LIMITE_ACABAR, LIMITE_FREQUENTES = 8, 10


def sugestoes(conn, uid: int, lista: int, hoje: date) -> dict:
    """Duas sugestões calmas, calculadas do histórico de compras que esta conta pode ver (as listas partilhadas e as suas):
    - `acabar`: produtos com um ritmo (a mediana dos intervalos, ≥ 5 dias) que já passou ~80% desse ritmo desde a última compra
      (e ainda não 3× o ritmo: se deixou de comprar, deixa de sugerir);
    - `frequentes`: produtos comprados em 2 ou mais dias nos últimos 90.
    Ficam de fora os escondidos (produto ou categoria), os marcados «não sugerir» e os que já estão por comprar na lista escolhida."""
    desde = (hoje - timedelta(days=JANELA_HISTORICO_DIAS)).isoformat()
    dias: dict[int, list[str]] = {}
    for r in conn.execute("SELECT product_id, dia FROM shop_history WHERE dia >= ? AND (escopo = 'partilhada' OR escopo = ?) ORDER BY dia", (desde, f"pessoal:{uid}")):
        dias.setdefault(r["product_id"], []).append(r["dia"])
    if not dias:
        return {"acabar": [], "frequentes": []}
    fora = {r["product_id"] for r in conn.execute("SELECT product_id FROM shop_user_products WHERE user_id = ? AND (oculto = 1 OR sem_sugestoes = 1)", (uid,))}
    fora |= {r["product_id"] for r in conn.execute("SELECT product_id FROM shop_items WHERE list_id = ? AND estado = 'pendente'", (lista,))}
    categorias_ocultas = {r["categoria"] for r in conn.execute("SELECT categoria FROM shop_user_categories WHERE user_id = ?", (uid,))}
    info = {p["id"]: p for p in conn.execute("SELECT id, nome, categoria, icone FROM shop_products WHERE id IN (%s)" % ",".join("?" * len(dias)), list(dias))}
    limite_freq = (hoje - timedelta(days=JANELA_FREQUENTES_DIAS)).isoformat()
    acabar, frequentes = [], []
    for pid, ds in dias.items():
        p = info.get(pid)
        if p is None or pid in fora or p["categoria"] in categorias_ocultas:
            continue
        datas = [date.fromisoformat(d) for d in ds]
        desde_ultima = (hoje - datas[-1]).days
        base = {"produto": pid, "nome": p["nome"], "categoria": p["categoria"], "icone": p["icone"], "ultima": ds[-1], "diasDesde": desde_ultima}
        if len(datas) >= MIN_COMPRAS_ACABAR:
            ritmo = statistics.median((b - a).days for a, b in zip(datas, datas[1:]))
            if ritmo >= INTERVALO_MIN_ACABAR and 0.8 * ritmo <= desde_ultima <= 3 * ritmo:
                acabar.append({**base, "intervaloDias": round(ritmo), "compras": len(datas), "_ordem": desde_ultima / ritmo})
                continue
        recentes = [d for d in ds if d >= limite_freq]
        if len(recentes) >= 2:
            frequentes.append({**base, "compras": len(recentes), "_ordem": len(recentes)})
    acabar.sort(key=lambda x: (-x["_ordem"], x["nome"].lower()))
    frequentes.sort(key=lambda x: (-x["_ordem"], -date.fromisoformat(x["ultima"]).toordinal(), x["nome"].lower()))
    limpo = lambda xs, n: [{k: v for k, v in x.items() if k != "_ordem"} for x in xs[:n]]
    return {"acabar": limpo(acabar, LIMITE_ACABAR), "frequentes": limpo(frequentes, LIMITE_FREQUENTES)}


DASHBOARD_ITENS = 5


def resumo_hoje(conn, uid: int, n: int = DASHBOARD_ITENS) -> dict:
    """O cartão do Hoje: alguns itens por comprar da lista «Casa» (pela ordem dos corredores). Marcar um como comprado faz aparecer o seguinte."""
    l = conn.execute("SELECT id, nome FROM shop_lists WHERE padrao = 1").fetchone()
    ordem = {c[0]: i for i, c in enumerate(cat.CATEGORIAS)}
    rows = conn.execute("SELECT i.id, i.product_id, i.quantidade, i.nota, p.nome, p.categoria, p.icone FROM shop_items i JOIN shop_products p ON p.id = i.product_id "
                        "WHERE i.list_id = ? AND i.estado = 'pendente'", (l["id"],)).fetchall()
    rows = sorted(rows, key=lambda r: (ordem.get(r["categoria"], 99), r["nome"].lower()))
    return {"lista": {"id": l["id"], "nome": l["nome"]}, "pendentes": len(rows),
            "itens": [{"item": r["id"], "produto": r["product_id"], "nome": r["nome"], "categoria": r["categoria"], "icone": r["icone"],
                       "quantidade": r["quantidade"], "nota": r["nota"]} for r in rows[:n]]}


# --- leitura -------------------------------------------------------------------------------------------------------------------

def visao(conn, uid: int, lista: int | None = None, hoje: date | None = None) -> dict:
    """Tudo o que o ecrã precisa num só pedido: listas, itens da lista escolhida (por corredor, e os comprados) e o catálogo."""
    listas = _listas(conn, uid)
    escolhida = next((l for l in listas if l["id"] == lista), None) if lista else next((l for l in listas if l["padrao"]), listas[0])
    if escolhida is None:
        raise _nao_encontrado("lista")
    ordem = {c[0]: i for i, c in enumerate(cat.CATEGORIAS)}
    nomes = dict(cat.CATEGORIAS)
    rows = conn.execute("SELECT i.*, p.nome, p.categoria, p.icone, u.nome AS por_nome, u.email AS por_email FROM shop_items i JOIN shop_products p ON p.id = i.product_id "
                        "LEFT JOIN pulse_users u ON u.id = i.adicionado_por WHERE i.list_id = ?", (escolhida["id"],)).fetchall()
    itens = [_linha(r) for r in rows]
    pendentes = sorted((i for i in itens if i["estado"] == "pendente"), key=lambda i: (ordem.get(i["categoria"], 99), i["nome"].lower()))
    grupos: list[dict] = []
    for i in pendentes:
        if not grupos or grupos[-1]["categoria"]["id"] != i["categoria"]:
            grupos.append({"categoria": {"id": i["categoria"], "nome": nomes.get(i["categoria"], i["categoria"])}, "itens": []})
        grupos[-1]["itens"].append(i)
    comprados = sorted((i for i in itens if i["estado"] == "comprado"), key=lambda i: -(i["compradoEm"] or 0))
    naLista = {i["produto"]: i for i in itens}
    marcas = {r["product_id"]: r for r in conn.execute("SELECT product_id, favorito, oculto FROM shop_user_products WHERE user_id = ?", (uid,))}
    produtos = []
    for p in conn.execute("SELECT * FROM shop_products ORDER BY nome COLLATE NOCASE"):
        m, it = marcas.get(p["id"]), naLista.get(p["id"])
        produtos.append({"id": p["id"], "nome": p["nome"], "categoria": p["categoria"], "icone": p["icone"], "builtin": bool(p["builtin"]), "criadoPor": p["criado_por"],
                         "favorito": bool(m and m["favorito"]), "oculto": bool(m and m["oculto"]), "item": it["id"] if it else None, "estado": it["estado"] if it else None})
    ocultas = {r["categoria"] for r in conn.execute("SELECT categoria FROM shop_user_categories WHERE user_id = ?", (uid,))}
    return {"categorias": [{"id": i, "nome": n, "oculta": i in ocultas} for i, n in cat.CATEGORIAS], "listas": listas, "lista": escolhida,
            "grupos": grupos, "comprados": comprados, "pendentes": len(pendentes), "produtos": produtos,
            "sugestoes": sugestoes(conn, uid, escolhida["id"], hoje or date.today())}
