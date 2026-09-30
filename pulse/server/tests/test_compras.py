import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from pulse import accounts, actions, compras_catalogo as cat, config, db
from pulse.accounts import ContaErro
from pulse.clients.dados import DadosClient
from pulse.main import create_app
from pulse.services import compras
from tests.conftest import FalsoDados

AGORA = datetime(2026, 9, 30, 10, 0, tzinfo=ZoneInfo("Europe/Lisbon"))
BRUNO, CAMILA = "pereirabmd@gmail.com", "camila@exemplo.pt"
UID: dict[str, int] = {}                                    # e-mail -> id, preenchido pela fixture `conn`
ICONES_JSON = Path(__file__).resolve().parents[2] / "web" / "src" / "assets" / "shop-icons.json"


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "teste-c.db"); db.migrate(c)
    UID.clear()
    for email, admin in ((BRUNO, True), (CAMILA, False)):
        UID[email] = accounts.criar_utilizador(c, email, "1234qweR", must_change=False, admin=admin)
    compras.sincronizar_catalogo(c, 1000)
    yield c
    c.close()


def prod(conn, nome):
    return conn.execute("SELECT id FROM shop_products WHERE nome = ?", (nome,)).fetchone()["id"]


def casa(conn):
    return conn.execute("SELECT id FROM shop_lists WHERE padrao = 1").fetchone()["id"]


# --- catálogo -------------------------------------------------------------------------------------------------------------------

def test_catalogo_e_completo_consistente_e_sem_duplicados():
    p = cat.produtos()
    assert 300 <= len(p) <= 400
    assert len({x["slug"] for x in p}) == len(p) and len({x["nome"].lower() for x in p}) == len(p)
    assert {x["categoria"] for x in p} <= cat.CATEGORIA_IDS and all(x["icone"] in cat.ICONES for x in p)
    assert set(cat.ICONE_DA_CATEGORIA) == cat.CATEGORIA_IDS and set(cat.ICONE_DA_CATEGORIA.values()) <= cat.ICONES
    assert all(1 <= len(x["nome"]) <= 80 for x in p)
    por = {c: sum(1 for x in p if x["categoria"] == c) for c in cat.CATEGORIA_IDS}
    assert all(por[c] > 0 for c in cat.CATEGORIA_IDS - {"outros"}) and por["outros"] == 0          # «Outros» é só para produtos próprios
    nomes = {x["nome"] for x in p}
    for pedido in ("Bacalhau", "Carne picada", "Leite meio-gordo", "Natas de cozinha", "Areia de gato aglomerante", "Ração seca para gato adulto", "Champô", "Detergente da loiça"):
        assert pedido in nomes


def test_icones_do_servidor_coincidem_com_os_da_web():
    web = json.loads(ICONES_JSON.read_text(encoding="utf-8"))
    assert set(web) == set(cat.ICONES)
    assert all(isinstance(v, list) and v and all(isinstance(d, str) and d for d in v) for v in web.values())


def test_slug():
    assert cat.slug("Pão de hambúrguer") == "pao-de-hamburguer" and cat.slug("Água tónica") == "agua-tonica"


def test_sincronizar_e_idempotente_e_respeita_o_que_o_utilizador_fez(conn):
    n = conn.execute("SELECT COUNT(*) FROM shop_products").fetchone()[0]
    assert n == len(cat.produtos()) and compras.sincronizar_catalogo(conn, 2000) == 0
    conn.execute("UPDATE shop_products SET nome = 'Leite antigo' WHERE slug = 'leite-meio-gordo'")
    compras.sincronizar_catalogo(conn, 3000)
    assert conn.execute("SELECT nome FROM shop_products WHERE slug = 'leite-meio-gordo'").fetchone()[0] == "Leite meio-gordo"      # o nome de série repõe-se; não duplica
    assert conn.execute("SELECT COUNT(*) FROM shop_products").fetchone()[0] == n


def test_produto_proprio_com_o_nome_de_um_de_serie_novo_ganha(tmp_path):
    c = db.connect(tmp_path / "teste-x.db"); db.migrate(c)
    uid = accounts.criar_utilizador(c, BRUNO, "1234qweR", must_change=False)
    compras.produto_criar(c, uid, "Maçã", "frutas-legumes", None, 1)
    compras.sincronizar_catalogo(c, 2)
    assert c.execute("SELECT COUNT(*) FROM shop_products WHERE nome = 'Maçã'").fetchone()[0] == 1
    assert c.execute("SELECT builtin FROM shop_products WHERE nome = 'Maçã'").fetchone()[0] == 0
    c.close()


# --- listas ---------------------------------------------------------------------------------------------------------------------

def test_a_casa_existe_e_as_pessoais_so_o_dono_as_ve(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    minha = compras.lista_criar(conn, b, "Churrasco", "pessoal")["id"]
    partilhada = compras.lista_criar(conn, c, "Festa", "partilhada")["id"]
    ids = lambda uid: {l["id"] for l in compras.visao(conn, uid)["listas"]}
    assert ids(b) == {casa(conn), minha, partilhada} and ids(c) == {casa(conn), partilhada}
    with pytest.raises(ContaErro) as e:
        compras.visao(conn, c, minha)
    assert e.value.status == 404                                                    # não se distingue de uma lista que não existe
    with pytest.raises(ContaErro):
        compras.adicionar(conn, c, minha, produto=prod(conn, "Leite meio-gordo"))
    assert compras.visao(conn, b)["lista"]["nome"] == "Casa"


def test_a_casa_nao_se_renomeia_nem_apaga_e_ha_limite(conn):
    b = UID[BRUNO]
    for f in (lambda: compras.lista_editar(conn, b, casa(conn), "X"), lambda: compras.lista_apagar(conn, b, casa(conn))):
        with pytest.raises(ContaErro) as e:
            f()
        assert e.value.codigo == "lista_padrao"
    for i in range(compras.MAX_LISTAS_POR_TIPO):
        compras.lista_criar(conn, b, f"L{i}", "pessoal")
    with pytest.raises(ContaErro) as e:
        compras.lista_criar(conn, b, "Mais uma", "pessoal")
    assert e.value.codigo == "demasiadas_listas"
    compras.lista_criar(conn, UID[CAMILA], "Dela", "pessoal")                  # o limite é por conta
    with pytest.raises(ContaErro):
        compras.lista_criar(conn, b, "  ", "pessoal")


def test_editar_e_apagar_lista_so_o_dono_da_pessoal(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    l = compras.lista_criar(conn, b, "Minha", "pessoal")["id"]
    for f in (lambda: compras.lista_editar(conn, c, l, "X"), lambda: compras.lista_apagar(conn, c, l)):
        with pytest.raises(ContaErro) as e:
            f()
        assert e.value.status == 404
    assert compras.lista_editar(conn, b, l, "  Churrasco  de sábado ")["nome"] == "Churrasco de sábado"
    compras.adicionar(conn, b, l, produto=prod(conn, "Bacalhau"))
    assert compras.lista_apagar(conn, b, l)["itens"] == 1
    assert conn.execute("SELECT COUNT(*) FROM shop_items WHERE list_id = ?", (l,)).fetchone()[0] == 0


# --- itens ----------------------------------------------------------------------------------------------------------------------

def test_adicionar_e_idempotente_e_nunca_soma_quantidade(conn):
    b, l, p = UID[BRUNO], casa(conn), prod(conn, "Leite meio-gordo")
    a = compras.adicionar(conn, b, l, produto=p, cid="cid-aaaa-0001")
    assert a["novo"] and a["quantidade"] is None and a["estado"] == "pendente" and a["nome"] == "Leite meio-gordo"
    assert compras.adicionar(conn, b, l, produto=p)["novo"] is False                        # já estava
    assert compras.adicionar(conn, b, l, produto=prod(conn, "Ovos"), cid="cid-aaaa-0001")["id"] == a["id"]     # o mesmo cid devolve o mesmo item
    assert conn.execute("SELECT COUNT(*) FROM shop_items").fetchone()[0] == 1
    assert compras.adicionar(conn, b, l, produto=p)["quantidade"] is None


def test_adicionar_por_nome_usa_o_existente_ou_cria_um_proprio(conn):
    b, l = UID[BRUNO], casa(conn)
    n = conn.execute("SELECT COUNT(*) FROM shop_products").fetchone()[0]
    e = compras.adicionar(conn, b, l, nome="  leite   MEIO-gordo ")
    assert e["produto"] == prod(conn, "Leite meio-gordo") and conn.execute("SELECT COUNT(*) FROM shop_products").fetchone()[0] == n
    novo = compras.adicionar(conn, b, l, nome="Leite de coco", categoria="mercearia")
    assert (novo["categoria"], novo["icone"]) == ("mercearia", "saco") and conn.execute("SELECT builtin FROM shop_products WHERE id = ?", (novo["produto"],)).fetchone()[0] == 0
    assert compras.adicionar(conn, b, l, nome="Coisa sem categoria")["categoria"] == "outros"
    for mau in ({"nome": "x", "categoria": "nada"}, {"nome": "x", "icone": "nada"}, {"nome": " "}, {}, {"produto": 1, "nome": "x"}):
        with pytest.raises(ContaErro):
            compras.adicionar(conn, b, l, **mau)
    with pytest.raises(ContaErro):
        compras.adicionar(conn, b, l, produto=999999)


def test_comprado_define_e_repetir_nao_muda(conn):
    b, c, l = UID[BRUNO], UID[CAMILA], casa(conn)
    i = compras.adicionar(conn, b, l, produto=prod(conn, "Ovos"))["id"]
    t1 = compras.comprado(conn, c, i, True, 100)
    assert t1["estado"] == "comprado" and t1["compradoEm"] == 100
    assert compras.comprado(conn, b, i, True, 999)["compradoEm"] == 100                      # repetir não muda quando nem por quem
    assert conn.execute("SELECT comprado_por FROM shop_items WHERE id = ?", (i,)).fetchone()[0] == c
    assert compras.comprado(conn, b, i, False)["estado"] == "pendente" and compras.comprado(conn, b, i, False)["compradoEm"] is None


def test_voltar_a_tocar_num_comprado_reativa_e_limpa_quantidade_e_nota(conn):
    b, l, p = UID[BRUNO], casa(conn), prod(conn, "Ovos")
    i = compras.adicionar(conn, b, l, produto=p)["id"]
    compras.detalhes(conn, b, i, 12, "grandes")
    compras.comprado(conn, b, i, True, 100)
    r = compras.adicionar(conn, b, l, produto=p)
    assert (r["id"], r["novo"], r["estado"], r["quantidade"], r["nota"]) == (i, True, "pendente", None, "")


def test_detalhes_define_quantidade_opcional_e_nota(conn):
    b, l = UID[BRUNO], casa(conn)
    i = compras.adicionar(conn, b, l, produto=prod(conn, "Leite meio-gordo"))["id"]
    r = compras.detalhes(conn, b, i, 6, "  1 L  marca  X ")
    assert (r["quantidade"], r["nota"]) == (6, "1 L marca X")
    assert compras.detalhes(conn, b, i, None, "")["quantidade"] is None
    for q, n in ((0, ""), (1000, ""), (1, "x" * 81)):
        with pytest.raises(ContaErro):
            compras.detalhes(conn, b, i, q, n)


def test_remover_devolve_o_que_era_e_restaurar_repoe(conn):
    b, l = UID[BRUNO], casa(conn)
    i = compras.adicionar(conn, b, l, produto=prod(conn, "Bacalhau"))["id"]
    compras.detalhes(conn, b, i, 2, "demolhado")
    antes = compras.remover(conn, b, i)
    assert antes["quantidade"] == 2 and compras.visao(conn, b)["pendentes"] == 0
    r = compras.restaurar(conn, b, l, [{"produto": antes["produto"], "quantidade": 2, "nota": "demolhado", "estado": "pendente"}])
    assert r == {"repostos": 1}
    back = compras.visao(conn, b)["grupos"][0]["itens"][0]
    assert (back["nome"], back["quantidade"], back["nota"]) == ("Bacalhau", 2, "demolhado")
    assert compras.restaurar(conn, b, l, [{"produto": antes["produto"]}]) == {"repostos": 0}         # repetir não duplica
    assert compras.restaurar(conn, b, l, [{"produto": 999999}]) == {"repostos": 0}


def test_limpar_comprados_so_apaga_os_comprados_e_da_para_desfazer(conn):
    b, l = UID[BRUNO], casa(conn)
    a, c = (compras.adicionar(conn, b, l, produto=prod(conn, n))["id"] for n in ("Ovos", "Bacalhau"))
    compras.comprado(conn, b, a, True, 50)
    r = compras.limpar_comprados(conn, b, l)
    assert [x["nome"] for x in r["removidos"]] == ["Ovos"] and compras.visao(conn, b)["pendentes"] == 1
    compras.restaurar(conn, b, l, [{"produto": x["produto"], "quantidade": x["quantidade"], "nota": x["nota"], "estado": x["estado"]} for x in r["removidos"]])
    v = compras.visao(conn, b)
    assert [x["nome"] for x in v["comprados"]] == ["Ovos"] and v["pendentes"] == 1


def test_mover_entre_listas_e_juncao(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    minha = compras.lista_criar(conn, b, "Minha", "pessoal")["id"]
    p = prod(conn, "Ovos")
    i = compras.adicionar(conn, b, minha, produto=p)["id"]
    m = compras.mover(conn, b, i, casa(conn))
    assert m["lista"] == casa(conn) and m["id"] == i
    j = compras.adicionar(conn, b, minha, produto=p)["id"]
    compras.comprado(conn, b, i, True, 10)                                              # na Casa está comprado; na Minha está por comprar
    r = compras.mover(conn, b, j, casa(conn))
    assert (r["id"], r["estado"]) == (i, "pendente") and conn.execute("SELECT COUNT(*) FROM shop_items WHERE product_id = ?", (p,)).fetchone()[0] == 1
    with pytest.raises(ContaErro):
        compras.mover(conn, c, i, minha)                                                # a lista pessoal do Bruno não é da Camila


def test_itens_de_listas_de_outros_sao_invisiveis(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    minha = compras.lista_criar(conn, b, "Minha", "pessoal")["id"]
    i = compras.adicionar(conn, b, minha, produto=prod(conn, "Ovos"))["id"]
    for f in (lambda: compras.comprado(conn, c, i, True), lambda: compras.remover(conn, c, i), lambda: compras.detalhes(conn, c, i, 1, ""),
              lambda: compras.limpar_comprados(conn, c, minha)):
        with pytest.raises(ContaErro) as e:
            f()
        assert e.value.status == 404


# --- produtos -------------------------------------------------------------------------------------------------------------------

def test_favoritos_e_ocultos_sao_por_conta(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    p = prod(conn, "Ovos")
    compras.favorito(conn, b, p, True); compras.ocultar(conn, c, p, True)
    vb = {x["nome"]: x for x in compras.visao(conn, b)["produtos"]}["Ovos"]
    vc = {x["nome"]: x for x in compras.visao(conn, c)["produtos"]}["Ovos"]
    assert (vb["favorito"], vb["oculto"], vc["favorito"], vc["oculto"]) == (True, False, False, True)
    compras.favorito(conn, b, p, False)
    assert conn.execute("SELECT COUNT(*) FROM shop_user_products WHERE user_id = ?", (b,)).fetchone()[0] == 0        # sem marcas, sem linha


def test_produto_proprio_editar_e_apagar_so_criador_ou_admin(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    p = compras.produto_criar(conn, c, "Tofu", "mercearia")["id"]
    with pytest.raises(ContaErro) as e:
        compras.produto_editar(conn, UID[BRUNO], False, p, "Tofu firme", None, None)      # Bruno sem ser admin (o parâmetro é explícito)
    assert e.value.codigo == "sem_permissao"
    assert compras.produto_editar(conn, c, False, p, "Tofu firme", "mercearia", "caixa")["nome"] == "Tofu firme"
    assert compras.produto_editar(conn, b, True, p, None, "frutas-legumes", None)["categoria"] == "frutas-legumes"     # o administrador pode
    with pytest.raises(ContaErro) as e:
        compras.produto_editar(conn, c, True, prod(conn, "Ovos"), "Ovos frescos", None, None)
    assert e.value.codigo == "produto_de_serie"
    compras.adicionar(conn, b, casa(conn), produto=p)
    assert compras.produto_apagar(conn, c, False, p)["itens"] == 1 and conn.execute("SELECT COUNT(*) FROM shop_items").fetchone()[0] == 0
    with pytest.raises(ContaErro):
        compras.produto_apagar(conn, c, False, prod(conn, "Ovos"))


def test_nome_de_produto_repetido_e_recusado_sem_distinguir_maiusculas(conn):
    with pytest.raises(ContaErro) as e:
        compras.produto_criar(conn, UID[BRUNO], "  OVOS ", "laticinios")
    assert e.value.codigo == "ja_existe"


def test_visao_agrupa_por_corredor_e_marca_o_estado_no_catalogo(conn):
    b, l = UID[BRUNO], casa(conn)
    for n in ("Champô", "Bacalhau", "Arroz agulha", "Leite meio-gordo", "Maçã"):
        compras.adicionar(conn, b, l, produto=prod(conn, n))
    compras.comprado(conn, b, compras.adicionar(conn, b, l, produto=prod(conn, "Ovos"))["id"], True, 5)
    v = compras.visao(conn, b)
    assert [g["categoria"]["id"] for g in v["grupos"]] == ["frutas-legumes", "mercearia", "laticinios", "peixe", "higiene"]
    assert v["pendentes"] == 5 and [x["nome"] for x in v["comprados"]] == ["Ovos"]
    por_nome = {p["nome"]: p for p in v["produtos"]}
    assert por_nome["Ovos"]["estado"] == "comprado" and por_nome["Maçã"]["estado"] == "pendente" and por_nome["Pera"]["item"] is None
    assert v["categorias"][0]["id"] == "frutas-legumes" and len(v["produtos"]) == len(cat.produtos())


# --- ações e API ----------------------------------------------------------------------------------------------------------------

def correr(conn, dados_falso, email, nome, params, **kw):
    ctx = actions.Contexto(DadosClient(dados_falso, FalsoDados.CHAVE), email, AGORA)
    return actions.executar(conn, ctx, nome, params, **kw)


def test_acoes_de_compras_fim_a_fim(conn, dados_falso):
    l = casa(conn)
    it = correr(conn, dados_falso, BRUNO, "compras.adicionar", {"lista": l, "nome": "Leite de coco", "categoria": "mercearia", "cid": "cid-bbbb-0002"})
    assert it["novo"] and it["adicionadoPor"] == BRUNO
    correr(conn, dados_falso, CAMILA, "compras.detalhes", {"item": it["id"], "quantidade": 2})
    assert correr(conn, dados_falso, CAMILA, "compras.comprado", {"item": it["id"], "comprado": True})["estado"] == "comprado"
    with pytest.raises(ContaErro) as e:
        correr(conn, dados_falso, BRUNO, "compras.limpar_comprados", {"lista": l})
    assert e.value.codigo == "confirmacao_necessaria"
    r = correr(conn, dados_falso, BRUNO, "compras.limpar_comprados", {"lista": l}, confirmado=True)
    assert [x["nome"] for x in r["removidos"]] == ["Leite de coco"]
    assert correr(conn, dados_falso, BRUNO, "compras.restaurar", {"lista": l, "itens": [{"produto": r["removidos"][0]["produto"], "estado": "comprado"}]}) == {"repostos": 1}
    acoes = [tuple(x) for x in conn.execute("SELECT utilizador, acao, resultado FROM pulse_activity ORDER BY id")]
    assert (BRUNO, "compras.adicionar", "ok") in acoes and (CAMILA, "compras.comprado", "ok") in acoes and FalsoDados.escritas == []       # nada foi ao dados-api


def test_acoes_recusam_parametros_invalidos(conn, dados_falso):
    for nome, p in (("compras.adicionar", {"lista": 1}), ("compras.adicionar", {"lista": 1, "produto": 1, "nome": "x"}), ("compras.detalhes", {"item": 1, "quantidade": 0}),
                    ("compras.comprado", {"item": 1}), ("compras.produto_editar", {"produto": 1}), ("compras.restaurar", {"lista": 1, "itens": [{"produto": 1, "estado": "x"}]})):
        with pytest.raises(ContaErro) as e:
            correr(conn, dados_falso, BRUNO, nome, p)
        assert e.value.codigo == "parametros_invalidos", (nome, p)


def test_erros_de_negocio_ficam_auditados_como_erro(conn, dados_falso):
    with pytest.raises(ContaErro):
        correr(conn, dados_falso, CAMILA, "compras.lista_apagar", {"lista": casa(conn)}, confirmado=True)
    assert [tuple(x) for x in conn.execute("SELECT acao, resultado, detalhe FROM pulse_activity")] == [("compras.lista_apagar", "erro", "lista_padrao")]


@pytest.fixture
def cliente(tmp_path, dados_falso):
    s = config.load({"PULSE_ENV": "test", "PULSE_DB_PATH": str(tmp_path / "teste-pulse.db"), "PULSE_DADOS_URL": dados_falso, "PULSE_SERVICE_KEY": FalsoDados.CHAVE, "PULSE_WEB_BASE_PATH": "/"})
    app = create_app(s); app.state.agora = lambda: AGORA
    with TestClient(app) as c:
        k = c.app.state.db()
        accounts.criar_utilizador(k, BRUNO, "1234qweR", must_change=False, admin=True); accounts.criar_utilizador(k, CAMILA, "1234qweR", must_change=False)
        k.close()
        yield c


def entrar(cliente, email):
    c = TestClient(cliente.app)
    assert c.post("/api/v1/auth/login", json={"email": email, "password": "1234qweR"}).status_code == 200
    return c


def test_api_o_catalogo_entra_no_arranque_e_a_lista_e_partilhada(cliente):
    b, c = entrar(cliente, BRUNO), entrar(cliente, CAMILA)
    v = b.get("/api/v1/shopping").json()
    assert len(v["produtos"]) == len(cat.produtos()) and v["lista"]["nome"] == "Casa"
    p = next(x["id"] for x in v["produtos"] if x["nome"] == "Ovos")
    H = {"X-Pulse-Client": "web"}
    r = b.post("/api/v1/actions/compras.adicionar", json={"params": {"lista": v["lista"]["id"], "produto": p}}, headers=H)
    assert r.status_code == 200 and r.json()["resultado"]["novo"] is True
    vc = c.get("/api/v1/shopping").json()                                                       # a Camila vê o que o Bruno pôs na Casa
    assert vc["pendentes"] == 1 and vc["grupos"][0]["itens"][0]["nome"] == "Ovos"


def test_api_lista_pessoal_de_outro_e_404_e_modulo_desativado_e_403(cliente):
    b, c = entrar(cliente, BRUNO), entrar(cliente, CAMILA)
    H = {"X-Pulse-Client": "web"}
    minha = b.post("/api/v1/actions/compras.lista_criar", json={"params": {"nome": "Minha"}}, headers=H).json()["resultado"]["id"]
    assert c.get(f"/api/v1/shopping?lista={minha}").status_code == 404
    assert c.get("/api/v1/shopping?lista=0").status_code in (400, 422)
    b.put("/api/v1/admin/modules", json={"modulos": {"compras": False}}, headers=H)
    r = c.get("/api/v1/shopping")
    assert (r.status_code, r.json()["erro"]["codigo"]) == (403, "modulo_desativado")
    assert c.post("/api/v1/actions/compras.adicionar", json={"params": {"lista": 1, "nome": "x"}}, headers=H).status_code == 403


# --- esconder categorias e sugestões (ADR-048) ----------------------------------------------------------------------------------

HOJE = datetime(2026, 9, 30).date()


def comprar(conn, uid, lista, nome, dia):
    """Põe e marca como comprado um produto num dia (o histórico regista-se ao marcar)."""
    i = compras.adicionar(conn, uid, lista, produto=prod(conn, nome))["id"]
    compras.comprado(conn, uid, i, True, 1_000, dia)
    compras.limpar_comprados(conn, uid, lista)                     # limpar a lista não pode apagar o histórico
    return i


def sug(conn, uid, lista=None):
    return compras.sugestoes(conn, uid, lista or casa(conn), HOJE)


def test_esconder_categoria_e_por_conta_e_reversivel(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    compras.categoria_ocultar(conn, b, "bebe", True)
    compras.categoria_ocultar(conn, b, "bebe", True)                                       # repetir não muda nada
    ocultas = lambda uid: {x["id"] for x in compras.visao(conn, uid)["categorias"] if x["oculta"]}
    assert ocultas(b) == {"bebe"} and ocultas(c) == set()
    assert len(compras.visao(conn, b)["produtos"]) == len(cat.produtos())                # o servidor não corta o catálogo: a interface é que o filtra
    compras.categoria_ocultar(conn, b, "bebe", False)
    assert ocultas(b) == set()
    with pytest.raises(ContaErro) as e:
        compras.categoria_ocultar(conn, b, "inventada", True)
    assert e.value.codigo == "categoria_invalida"


def test_o_que_ja_esta_na_lista_continua_visivel_mesmo_com_a_categoria_escondida(conn):
    b = UID[BRUNO]
    compras.adicionar(conn, b, casa(conn), produto=prod(conn, "Fraldas"))
    compras.categoria_ocultar(conn, b, "bebe", True)
    v = compras.visao(conn, b)
    assert [g["categoria"]["id"] for g in v["grupos"]] == ["bebe"] and v["pendentes"] == 1


def test_historico_regista_uma_vez_por_dia_e_desmarcar_retira_o_de_hoje(conn):
    b, l, p = UID[BRUNO], casa(conn), prod(conn, "Ovos")
    i = compras.adicionar(conn, b, l, produto=p)["id"]
    compras.comprado(conn, b, i, True, 100, "2026-09-30"); compras.comprado(conn, b, i, True, 100, "2026-09-30")
    n = lambda: conn.execute("SELECT COUNT(*) FROM shop_history").fetchone()[0]
    assert n() == 1
    compras.comprado(conn, b, i, False, None, "2026-09-30")                                 # toque enganado
    assert n() == 0
    compras.comprado(conn, b, i, True, 100, "2026-09-30")
    compras.remover(conn, b, i)
    assert n() == 1                                                                         # remover o item não apaga o histórico


def test_historico_e_por_ambito_partilhado_ou_pessoal(conn):
    b, c = UID[BRUNO], UID[CAMILA]
    minha = compras.lista_criar(conn, b, "Minha", "pessoal")["id"]
    for dia in ("2026-09-01", "2026-09-10"):
        comprar(conn, b, casa(conn), "Ovos", dia)                 # partilhada: toda a casa
        comprar(conn, b, minha, "Bacalhau", dia)                   # pessoal: só o Bruno
    assert {x["nome"] for x in sug(conn, b)["frequentes"]} == {"Ovos", "Bacalhau"}
    assert {x["nome"] for x in sug(conn, c)["frequentes"]} == {"Ovos"}
    assert {r[0] for r in conn.execute("SELECT DISTINCT escopo FROM shop_history")} == {"partilhada", f"pessoal:{b}"}


def test_frequentes_so_com_duas_compras_nos_ultimos_90_dias(conn):
    b, l = UID[BRUNO], casa(conn)
    comprar(conn, b, l, "Ovos", "2026-09-20")                      # 1 compra: não chega
    comprar(conn, b, l, "Leite meio-gordo", "2026-09-01"); comprar(conn, b, l, "Leite meio-gordo", "2026-09-20")
    comprar(conn, b, l, "Bacalhau", "2026-05-01"); comprar(conn, b, l, "Bacalhau", "2026-05-10")   # há > 90 dias
    f = sug(conn, b)["frequentes"]
    assert [x["nome"] for x in f] == ["Leite meio-gordo"] and f[0]["compras"] == 2 and f[0]["ultima"] == "2026-09-20" and f[0]["diasDesde"] == 10


def test_a_acabar_limites_do_ritmo(conn):
    b, l = UID[BRUNO], casa(conn)
    def ritmo(nome, ultima_compra, intervalo, vezes=4):
        d = datetime.fromisoformat(ultima_compra)
        for k in range(vezes):
            comprar(conn, b, l, nome, (d - timedelta(days=intervalo * k)).date().isoformat())
    ritmo("Café moído", "2026-09-16", 14)             # 14 dias desde a última, ritmo 14: já é a altura
    ritmo("Detergente da loiça", "2026-09-25", 14)    # 5 dias desde a última: ainda cedo (< 80% do ritmo)
    ritmo("Champô", "2026-08-01", 14)                 # 60 dias, > 3× o ritmo: deixou de comprar, não insiste
    ritmo("Pão", "2026-09-27", 2)                     # ritmo curto (< 5 dias): não é «a acabar»
    a = sug(conn, b)
    assert [x["nome"] for x in a["acabar"]] == ["Café moído"]
    x = a["acabar"][0]
    assert (x["intervaloDias"], x["diasDesde"], x["compras"]) == (14, 14, 4)
    assert "Café moído" not in {y["nome"] for y in a["frequentes"]}                       # não aparece nas duas


def test_sugestoes_respeitam_escondidos_ignorados_e_o_que_ja_esta_na_lista(conn):
    b, l = UID[BRUNO], casa(conn)
    for nome in ("Ovos", "Leite meio-gordo", "Bacalhau", "Fraldas", "Champô"):
        for dia in ("2026-09-05", "2026-09-20"):
            comprar(conn, b, l, nome, dia)
    assert {x["nome"] for x in sug(conn, b)["frequentes"]} == {"Ovos", "Leite meio-gordo", "Bacalhau", "Fraldas", "Champô"}
    compras.sugestao_ignorar(conn, b, prod(conn, "Ovos"), True)
    compras.ocultar(conn, b, prod(conn, "Bacalhau"), True)
    compras.categoria_ocultar(conn, b, "bebe", True)
    compras.adicionar(conn, b, l, produto=prod(conn, "Champô"))
    assert {x["nome"] for x in sug(conn, b)["frequentes"]} == {"Leite meio-gordo"}
    assert {x["nome"] for x in sug(conn, UID[CAMILA])["frequentes"]} == {"Ovos", "Leite meio-gordo", "Bacalhau", "Fraldas"}      # a Camila não herda os «não sugerir» nem os escondidos do Bruno; o Champô já está na lista da Casa
    compras.sugestao_ignorar(conn, b, prod(conn, "Ovos"), False)
    assert "Ovos" in {x["nome"] for x in sug(conn, b)["frequentes"]}
    assert conn.execute("SELECT COUNT(*) FROM shop_user_products WHERE user_id = ? AND product_id = ?", (b, prod(conn, "Ovos"))).fetchone()[0] == 0


def test_apagar_produto_apaga_o_seu_historico_e_sem_historico_nao_ha_sugestoes(conn):
    b, l = UID[BRUNO], casa(conn)
    assert sug(conn, b) == {"acabar": [], "frequentes": []}
    p = compras.produto_criar(conn, b, "Tofu", "mercearia")["id"]
    for dia in ("2026-09-01", "2026-09-20"):
        i = compras.adicionar(conn, b, l, produto=p)["id"]; compras.comprado(conn, b, i, True, 1, dia); compras.limpar_comprados(conn, b, l)
    assert [x["nome"] for x in sug(conn, b)["frequentes"]] == ["Tofu"]
    compras.produto_apagar(conn, b, False, p)
    assert conn.execute("SELECT COUNT(*) FROM shop_history").fetchone()[0] == 0 and sug(conn, b)["frequentes"] == []


def test_visao_inclui_as_sugestoes_e_a_lista_escolhida_conta(conn):
    b, l = UID[BRUNO], casa(conn)
    for dia in ("2026-09-05", "2026-09-20"):
        comprar(conn, b, l, "Ovos", dia)
    assert [x["nome"] for x in compras.visao(conn, b, None, HOJE)["sugestoes"]["frequentes"]] == ["Ovos"]
    compras.adicionar(conn, b, l, produto=prod(conn, "Ovos"))
    assert compras.visao(conn, b, None, HOJE)["sugestoes"]["frequentes"] == []             # já está na lista
    outra = compras.lista_criar(conn, b, "Outra", "pessoal")["id"]
    assert [x["nome"] for x in compras.visao(conn, b, outra, HOJE)["sugestoes"]["frequentes"]] == ["Ovos"]


def test_acoes_e_api_das_categorias_e_sugestoes(cliente):
    b = entrar(cliente, BRUNO)
    H = {"X-Pulse-Client": "web"}
    v = b.get("/api/v1/shopping").json()
    assert v["sugestoes"] == {"acabar": [], "frequentes": []} and all(c["oculta"] is False for c in v["categorias"])
    assert b.post("/api/v1/actions/compras.categoria_ocultar", json={"params": {"categoria": "bebe", "valor": True}}, headers=H).status_code == 200
    assert {c["id"] for c in b.get("/api/v1/shopping").json()["categorias"] if c["oculta"]} == {"bebe"}
    assert b.post("/api/v1/actions/compras.categoria_ocultar", json={"params": {"categoria": "nada", "valor": True}}, headers=H).status_code == 400
    p = next(x["id"] for x in v["produtos"] if x["nome"] == "Ovos")
    assert b.post("/api/v1/actions/compras.sugestao_ignorar", json={"params": {"produto": p, "valor": True}}, headers=H).status_code == 200
    item = b.post("/api/v1/actions/compras.adicionar", json={"params": {"lista": v["lista"]["id"], "produto": p}}, headers=H).json()["resultado"]["id"]
    assert b.post("/api/v1/actions/compras.comprado", json={"params": {"item": item, "comprado": True}}, headers=H).status_code == 200
    k = cliente.app.state.db()
    assert k.execute("SELECT dia FROM shop_history").fetchone()[0] == "2026-09-30"          # o dia vem do relógio do servidor
    k.close()


# --- última chamada (ADR-076) --------------------------------------------------------------------------------------------------

class _Canal:
    nome = "falso"

    def __init__(self):
        self.enviados = []

    def enviar(self, token, evento):
        self.enviados.append((token, evento.titulo, evento.corpo))


def _ultima(conn, email, mensagem="", agora=AGORA, canais=None):
    ctx = actions.Contexto(None, email, agora, canais=canais)
    return actions.executar(conn, ctx, "compras.ultima_chamada", {"lista": casa(conn), "mensagem": mensagem}, confirmado=True)


def test_ultima_chamada_avisa_todos_menos_quem_a_fez_e_so_uma_vez(conn):
    canal = _Canal()
    for email in (BRUNO, CAMILA):
        conn.execute("INSERT INTO pulse_devices (user_id, fcm_token, criado, ultimo_uso) VALUES (?,?,1,1)", (UID[email], f"token-{email.split('@')[0]}-0123456789"))
    compras.adicionar(conn, UID[BRUNO], casa(conn), prod(conn, "Leite meio-gordo"))
    r = _ultima(conn, BRUNO, "saio às 18h", canais=[canal])
    assert r["avisados"] == 1
    assert [(t, ti) for t, ti, _ in canal.enviados] == [("token-camila-0123456789", "Última chamada — Casa")]
    assert "saio às 18h" in canal.enviados[0][2] and "1 por comprar" in canal.enviados[0][2]
    with pytest.raises(ContaErro) as e:                                     # só uma por ida às compras
        _ultima(conn, CAMILA)
    assert e.value.codigo == "ja_avisado" and len(canal.enviados) == 1
    v = compras.visao(conn, UID[CAMILA], agora=int(AGORA.timestamp()) + 60)
    assert v["ultimaChamada"]["mensagem"] == "saio às 18h" and v["ultimaChamada"]["por"]


def test_ultima_chamada_reabre_com_limpar_comprados_e_caduca_em_12_h(conn):
    _ultima(conn, BRUNO)
    t = int(AGORA.timestamp())
    assert compras.visao(conn, UID[BRUNO], agora=t + 11 * 3600)["ultimaChamada"] is not None
    assert compras.visao(conn, UID[BRUNO], agora=t + 12 * 3600 + 1)["ultimaChamada"] is None        # caducou
    _ultima(conn, CAMILA, agora=AGORA + timedelta(hours=13))                                        # e já se pode fazer outra
    compras.limpar_comprados(conn, UID[BRUNO], casa(conn))
    assert compras.visao(conn, UID[BRUNO], agora=t + 13 * 3600 + 60)["ultimaChamada"] is None
    _ultima(conn, BRUNO, agora=AGORA + timedelta(hours=14))


def test_ultima_chamada_so_em_listas_partilhadas_e_a_acao_pede_confirmacao(conn):
    pessoal = compras.lista_criar(conn, UID[BRUNO], "Minha", "pessoal")["id"]
    with pytest.raises(ContaErro) as e:
        compras.ultima_chamada(conn, UID[BRUNO], pessoal)
    assert e.value.codigo == "lista_pessoal"
    with pytest.raises(ContaErro) as e:
        compras.ultima_chamada(conn, UID[BRUNO], casa(conn), "x" * 121)
    assert e.value.codigo == "mensagem_grande"
    with pytest.raises(ContaErro) as e:
        actions.executar(conn, actions.Contexto(None, BRUNO, AGORA), "compras.ultima_chamada", {"lista": casa(conn)})
    assert e.value.codigo == "confirmacao_necessaria"
