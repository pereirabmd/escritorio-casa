"""Catálogo de série das Compras (ADR-047): produtos de uma casa normal, por corredor de supermercado.

Cada produto tem um `slug` estável (derivado do nome **no momento em que entra aqui** e guardado na base): mudar o nome de um produto
de série mais tarde NÃO cria um duplicado se se indicar o slug antigo com `nome|icone|slug`. Acrescentar produtos é seguro; o
arranque só insere o que falta e atualiza nome, categoria e ícone dos de série (nunca mexe em favoritos, ocultos ou produtos próprios).
"""

from __future__ import annotations

import re
import unicodedata

# (id, nome) por ordem de corredor
CATEGORIAS: tuple[tuple[str, str], ...] = (
    ("frutas-legumes", "Frutas e legumes"), ("padaria", "Padaria e pastelaria"), ("mercearia", "Mercearia"), ("laticinios", "Laticínios e ovos"),
    ("carne", "Carne"), ("peixe", "Peixe"), ("congelados", "Congelados"), ("bebidas", "Bebidas"), ("higiene", "Higiene pessoal"),
    ("limpeza", "Limpeza"), ("casa", "Casa e bazar"), ("bebe", "Bebé e crianças"), ("gato", "Gato"), ("outros", "Outros"),
)
CATEGORIA_IDS = {c[0] for c in CATEGORIAS}

# ícone por omissão de cada categoria (produtos próprios sem ícone escolhido)
ICONE_DA_CATEGORIA = {
    "frutas-legumes": "fruta", "padaria": "pao", "mercearia": "saco", "laticinios": "leite", "carne": "carne", "peixe": "peixe", "congelados": "congelado",
    "bebidas": "garrafa", "higiene": "dispensador", "limpeza": "spray", "casa": "caixa", "bebe": "biberao", "gato": "gato", "outros": "cesto",
}

# os ícones existentes (a fonte é web/src/assets/shop-icons.json; um teste garante que coincidem)
ICONES = frozenset("""fruta citrico cacho banana folhas raiz tomate batata cebola pimento cogumelo pao croissant bolo saco massa lata frasco garrafa oleo caixa
cereais cafe chocolate snack biscoito ovo sal moinho leite queijo iogurte manteiga carne frango enchido peixe camarao congelado gelado pizza agua sumo
cerveja vinho papel dispensador tubo escova lamina algodao penso gota sol spray cruz balde esponja luva lixo roupa pastilha inseto pilha lampada fogo fita
fralda biberao gato areia pata cesto""".split())

_RAW: dict[str, str] = {
    "frutas-legumes": """
Maçã|fruta; Pera|fruta; Banana|banana; Laranja|citrico; Tangerina|citrico; Limão|citrico; Uvas|cacho; Morangos|fruta; Kiwi|fruta; Ananás|fruta;
Melancia|citrico; Melão|citrico; Pêssego|fruta; Ameixa|fruta; Abacate|fruta; Mirtilos|cacho; Alface|folhas; Espinafres|folhas; Couve|folhas;
Rúcula|folhas; Brócolos|folhas; Couve-flor|folhas; Tomate|tomate; Pepino|folhas; Cenoura|raiz; Beterraba|raiz; Nabo|raiz; Batata|batata;
Batata-doce|batata; Cebola|cebola; Alho|cebola; Alho-francês|folhas; Pimento|pimento; Curgete|folhas; Beringela|pimento; Abóbora|citrico;
Cogumelos|cogumelo; Milho|folhas; Salsa|folhas; Coentros|folhas; Hortelã|folhas
""",
    "padaria": """
Pão|pao; Pão de forma|pao; Pão integral|pao; Pão de leite|pao; Broa|pao; Baguete|pao; Pão de hambúrguer|pao; Croissants|croissant;
Pastéis de nata|bolo; Bolo|bolo; Bolo de arroz|bolo
""",
    "mercearia": """
Arroz agulha|saco; Arroz carolino|saco; Arroz basmati|saco; Esparguete|massa; Massa penne|massa; Massa fusilli|massa; Massa para sopa|massa;
Massa lasanha|massa; Couscous|saco; Farinha de trigo|saco; Farinha com fermento|saco; Farinha maizena|saco; Pão ralado|saco; Flocos de aveia|cereais;
Flocos de milho|cereais; Granola|cereais; Cereais de pequeno-almoço|cereais; Tostas|biscoito; Tortilhas|pao;
Bolacha Maria|biscoito; Bolacha de água e sal|biscoito; Bolacha recheada|biscoito; Batatas fritas|snack; Batata palha|snack; Pipocas|snack;
Amendoins|snack; Frutos secos|snack; Nozes|snack; Amêndoas|snack; Passas de uva|snack; Barras de cereais|chocolate; Gomas|snack;
Atum em lata|lata; Sardinhas em lata|lata; Cavala em lata|lata; Feijão preto|lata; Feijão-frade|lata; Feijão vermelho|lata; Grão-de-bico|lata;
Lentilhas|lata; Milho doce|lata; Ervilhas|lata; Cogumelos em lata|lata; Tomate pelado|lata; Azeitonas|frasco; Pêssego em calda|lata; Ananás em calda|lata;
Azeite|oleo; Óleo alimentar|oleo; Vinagre|garrafa; Sal fino|sal; Sal grosso|sal; Pimenta|moinho; Açúcar|saco; Açúcar em pó|saco; Adoçante|caixa;
Polpa de tomate|lata; Concentrado de tomate|tubo; Molho de tomate|frasco; Molho pesto|frasco; Ketchup|frasco; Maionese|frasco; Mostarda|frasco;
Molho de soja|garrafa; Caldo de legumes|caixa; Caldo de carne|caixa; Colorau|moinho; Orégãos|moinho; Louro|moinho; Canela|moinho; Noz-moscada|moinho;
Alho em pó|moinho; Fermento|caixa; Levedura|caixa; Bicarbonato de sódio|caixa; Gelatina|caixa;
Café moído|cafe; Café em cápsulas|cafe; Chá preto|cafe; Chá de camomila|cafe; Chá de menta|cafe; Chocolate em pó|chocolate; Cacau em pó|chocolate;
Compota|frasco; Mel|frasco; Manteiga de amendoim|frasco; Creme de chocolate para barrar|frasco; Chocolate de leite|chocolate; Chocolate negro|chocolate
""",
    "laticinios": """
Leite meio-gordo|leite; Leite magro|leite; Leite gordo|leite; Leite sem lactose|leite; Leite achocolatado|leite; Leite condensado|lata;
Bebida de aveia|leite; Bebida de soja|leite; Bebida de amêndoa|leite; Natas de cozinha|leite; Natas para bater|leite;
Manteiga|manteiga; Margarina|manteiga; Queijo fatiado|queijo; Queijo ralado|queijo; Queijo fresco|queijo; Queijo mozzarella|queijo; Requeijão|queijo;
Iogurte natural|iogurte; Iogurte grego|iogurte; Iogurtes de fruta|iogurte; Iogurtes líquidos|iogurte; Pudim|iogurte; Ovos|ovo
""",
    "carne": """
Frango inteiro|frango; Peito de frango|frango; Coxas de frango|frango; Perna de frango|frango; Peito de peru|frango; Carne picada|carne;
Bifes de vaca|carne; Carne para estufar|carne; Hambúrgueres|carne; Bifes de porco|carne; Febras de porco|carne; Costeletas de porco|carne;
Lombo de porco|carne; Entrecosto|carne; Salsichas|enchido; Chouriço|enchido; Fiambre|enchido; Presunto|enchido; Bacon|enchido
""",
    "peixe": """
Bacalhau|peixe; Bacalhau demolhado|peixe; Salmão|peixe; Salmão fumado|peixe; Pescada|peixe; Filetes de pescada|peixe; Dourada|peixe; Robalo|peixe;
Carapau|peixe; Sardinhas frescas|peixe; Lulas|camarao; Polvo|camarao; Camarão|camarao; Mexilhões|camarao
""",
    "congelados": """
Ervilhas congeladas|congelado; Espinafres congelados|congelado; Brócolos congelados|congelado; Mistura de legumes congelados|congelado;
Batatas fritas congeladas|congelado; Pizza congelada|pizza; Douradinhos|peixe; Nuggets de frango|frango; Camarão congelado|camarao;
Fruta congelada|congelado; Massa folhada|congelado; Pão de alho|pao; Gelado|gelado; Gelo|congelado
""",
    "bebidas": """
Água|agua; Água com gás|agua; Água tónica|garrafa; Sumo de laranja|sumo; Sumo de fruta|sumo; Sumo de maçã|sumo; Refrigerante de cola|garrafa;
Refrigerante de laranja|garrafa; Refrigerante de limão|garrafa; Ice tea|garrafa; Cerveja|cerveja; Cerveja sem álcool|cerveja; Vinho tinto|vinho;
Vinho branco|vinho; Vinho verde|vinho; Espumante|vinho
""",
    "higiene": """
Champô|dispensador; Champô anticaspa|dispensador; Amaciador de cabelo|dispensador; Gel de cabelo|frasco; Laca|spray; Tinta de cabelo|caixa;
Gel de banho|dispensador; Sabonete em barra|caixa; Sabonete líquido de mãos|dispensador; Sabonete íntimo|dispensador; Desodorizante|spray;
Creme hidratante de corpo|frasco; Creme de rosto|frasco; Protetor solar|sol; Gel desinfetante de mãos|dispensador; Removedor de maquilhagem|frasco;
Pasta de dentes|tubo; Escova de dentes|escova; Colutório|garrafa; Fio dentário|caixa; Espuma de barbear|spray; Lâminas de barbear|lamina;
Cera depilatória|frasco; Corta-unhas|lamina; Lixa de unhas|lamina; Papel higiénico|papel; Lenços de papel|caixa; Toalhetes húmidos|caixa;
Algodão|algodao; Discos de algodão|algodao; Cotonetes|algodao; Pensos rápidos|penso; Pensos higiénicos|gota; Tampões|gota; Protetores diários|gota;
Acetona|frasco
""",
    "limpeza": """
Detergente da loiça|dispensador; Pastilhas para máquina da loiça|pastilha; Sal para máquina da loiça|sal; Abrilhantador|garrafa; Esponjas|esponja;
Esfregões|esponja; Luvas de limpeza|luva; Detergente da roupa (líquido)|roupa; Detergente da roupa (cápsulas)|pastilha; Amaciador de roupa|roupa;
Tira-nódoas|spray; Lixívia|garrafa; Multiusos|spray; Limpa-vidros|spray; Limpa-casas de banho|spray; Desengordurante|spray; Anticalcário|spray;
Limpa-chão|balde; Limpa-fornos|spray; Desinfetante|spray; Álcool etílico|garrafa; Detergente WC|garrafa; Pastilhas WC|pastilha; Desentupidor|garrafa;
Rolo de cozinha|papel; Guardanapos de papel|caixa; Panos de microfibra|esponja; Pano multiusos|esponja; Papel de alumínio|papel; Película aderente|papel;
Papel vegetal|papel; Sacos do lixo pequenos|lixo; Sacos do lixo grandes|lixo; Sacos de congelação|lixo; Sacos de aspirador|caixa; Ambientador|spray;
Inseticida|inseto; Toalhetes desinfetantes|caixa
""",
    "casa": """
Pilhas AA|pilha; Pilhas AAA|pilha; Lâmpadas|lampada; Velas|fogo; Fósforos|fogo; Isqueiro|fogo; Fita-cola|fita; Cola|tubo; Pratos descartáveis|caixa;
Copos descartáveis|caixa; Repelente de mosquitos|inseto
""",
    "bebe": """
Fraldas|fralda; Toalhetes de bebé|caixa; Creme de fraldas|tubo; Champô de bebé|dispensador; Gel de banho de bebé|dispensador; Leite de bebé|biberao;
Papa infantil|cereais; Boiões de fruta|frasco; Cereais infantis|cereais
""",
    "gato": """
Ração seca para gato adulto|gato; Ração seca para gato esterilizado|gato; Ração seca para gatinho|gato; Comida húmida em saquetas|gato;
Comida húmida em patê|gato; Comida húmida em latas|lata; Snacks para gato|pata; Malte para gatos|tubo; Erva-gateira|folhas; Leite para gatos|leite;
Areia de gato aglomerante|areia; Areia de gato de sílica|areia; Areia de gato biodegradável|areia; Sacos para areia|lixo; Desodorizante de areia|spray;
Desparasitante (pipeta)|tubo
""",
}


def slug(nome: str) -> str:
    s = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def produtos() -> list[dict]:
    """Os produtos de série, por corredor: `{slug, nome, categoria, icone}`."""
    out = []
    for cat, bloco in _RAW.items():
        for item in (x.strip() for x in bloco.replace("\n", " ").split(";")):
            if not item:
                continue
            partes = item.split("|")
            nome, icone = partes[0].strip(), partes[1].strip()
            out.append({"slug": partes[2].strip() if len(partes) > 2 else slug(nome), "nome": nome, "categoria": cat, "icone": icone})
    return out
