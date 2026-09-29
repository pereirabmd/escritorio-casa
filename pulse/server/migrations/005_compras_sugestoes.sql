-- Compras: esconder categorias inteiras e sugestões (ADR-048). Tudo por conta, excepto o histórico da lista partilhada.

-- há linha = a categoria está escondida para essa conta (os itens que já estão nas listas continuam visíveis)
CREATE TABLE shop_user_categories (
    user_id   INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    categoria TEXT NOT NULL CHECK (length(categoria) BETWEEN 1 AND 40),
    PRIMARY KEY (user_id, categoria)
) WITHOUT ROWID;

-- «Não sugerir este produto» (por conta)
ALTER TABLE shop_user_products ADD COLUMN sem_sugestoes INTEGER NOT NULL DEFAULT 0 CHECK (sem_sugestoes IN (0, 1));

-- Um registo por produto, por âmbito e por dia em que foi comprado (marcar comprado várias vezes no mesmo dia conta uma).
-- `escopo`: 'partilhada' (compras das listas partilhadas: toda a casa as vê) ou 'pessoal:<id da conta>' (só o dono).
-- Sobrevive a «Limpar comprados», a remover itens e a apagar listas: é o que alimenta as sugestões.
CREATE TABLE shop_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES shop_products (id) ON DELETE CASCADE,
    escopo     TEXT NOT NULL CHECK (escopo = 'partilhada' OR escopo GLOB 'pessoal:[0-9]*'),
    dia        TEXT NOT NULL CHECK (dia GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    user_id    INTEGER REFERENCES pulse_users (id) ON DELETE SET NULL,
    UNIQUE (product_id, escopo, dia)
);
CREATE INDEX shop_history_escopo ON shop_history (escopo, dia);
