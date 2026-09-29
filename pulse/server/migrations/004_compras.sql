-- Compras (ADR-047): módulo exclusivo do Pulse. Catálogo (de série + próprios), listas (a «Casa» partilhada e listas pessoais) e itens.

CREATE TABLE shop_products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT UNIQUE CHECK (slug IS NULL OR length(slug) BETWEEN 1 AND 80),      -- só os de série; estável mesmo que o nome mude
    nome        TEXT NOT NULL COLLATE NOCASE CHECK (length(nome) BETWEEN 1 AND 80),
    categoria   TEXT NOT NULL CHECK (length(categoria) BETWEEN 1 AND 40),
    icone       TEXT NOT NULL CHECK (length(icone) BETWEEN 1 AND 40),
    builtin     INTEGER NOT NULL DEFAULT 0 CHECK (builtin IN (0, 1)),
    criado_por  INTEGER REFERENCES pulse_users (id) ON DELETE SET NULL,
    criado      INTEGER NOT NULL
);
CREATE UNIQUE INDEX shop_products_nome ON shop_products (nome);                          -- sem distinguir maiúsculas: «Leite» e «leite» são o mesmo produto

-- favoritos e produtos escondidos são por conta (o catálogo é comum); só há linha quando algo foi marcado
CREATE TABLE shop_user_products (
    user_id    INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES shop_products (id) ON DELETE CASCADE,
    favorito   INTEGER NOT NULL DEFAULT 0 CHECK (favorito IN (0, 1)),
    oculto     INTEGER NOT NULL DEFAULT 0 CHECK (oculto IN (0, 1)),
    PRIMARY KEY (user_id, product_id)
) WITHOUT ROWID;

CREATE TABLE shop_lists (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    nome    TEXT NOT NULL CHECK (length(nome) BETWEEN 1 AND 60),
    tipo    TEXT NOT NULL CHECK (tipo IN ('partilhada', 'pessoal')),
    dono_id INTEGER REFERENCES pulse_users (id) ON DELETE CASCADE,                       -- só as pessoais; apagar a conta apaga as suas listas
    padrao  INTEGER NOT NULL DEFAULT 0 CHECK (padrao IN (0, 1)),                         -- a «Casa»: não se apaga nem renomeia
    criado  INTEGER NOT NULL,
    CHECK ((tipo = 'partilhada' AND dono_id IS NULL) OR (tipo = 'pessoal' AND dono_id IS NOT NULL))
);
INSERT INTO shop_lists (nome, tipo, dono_id, padrao, criado) VALUES ('Casa', 'partilhada', NULL, 1, CAST(strftime('%s', 'now') AS INTEGER));

-- um produto aparece uma só vez por lista; «comprado» é um estado do mesmo item (voltar a tocar no produto reativa-o)
CREATE TABLE shop_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    list_id       INTEGER NOT NULL REFERENCES shop_lists (id) ON DELETE CASCADE,
    product_id    INTEGER NOT NULL REFERENCES shop_products (id) ON DELETE CASCADE,
    quantidade    INTEGER CHECK (quantidade IS NULL OR quantidade BETWEEN 1 AND 999),   -- opcional: nunca se altera com um toque no catálogo
    nota          TEXT NOT NULL DEFAULT '' CHECK (length(nota) <= 80),
    estado        TEXT NOT NULL DEFAULT 'pendente' CHECK (estado IN ('pendente', 'comprado')),
    adicionado_por INTEGER REFERENCES pulse_users (id) ON DELETE SET NULL,
    criado        INTEGER NOT NULL,
    comprado_em   INTEGER,
    comprado_por  INTEGER REFERENCES pulse_users (id) ON DELETE SET NULL,
    cid           TEXT UNIQUE CHECK (cid IS NULL OR length(cid) BETWEEN 8 AND 64),
    UNIQUE (list_id, product_id)
);
CREATE INDEX shop_items_lista ON shop_items (list_id, estado);
