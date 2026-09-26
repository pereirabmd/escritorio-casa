-- App financas (gestão financeira pessoal). Tabelas prefixadas `financas_`.
-- Datas em texto ISO ('AAAA-MM-DD'); estados (pendente / vencido / pago) NÃO se
-- guardam: derivam-se de data_pagamento e data_vencimento.
CREATE TABLE financas_categorias (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
    cor  TEXT NOT NULL CHECK (cor GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]')
);

INSERT INTO financas_categorias (nome, cor) VALUES
    ('Habitação',   '#476D7C'),
    ('Alimentação', '#D9A441'),
    ('Transportes', '#6C77A8'),
    ('Lazer',       '#AA6F8E'),
    ('Saúde',       '#4F9C8C'),
    ('Rendimentos', '#239B6D'),
    ('Outros',      '#8A918E');

-- Tabela unificada: despesas e rendimentos (o salário é um lançamento `rendimento`).
CREATE TABLE financas_lancamentos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo            TEXT    NOT NULL CHECK (tipo IN ('despesa', 'rendimento')),
    descricao       TEXT    NOT NULL,
    valor           REAL    NOT NULL CHECK (valor > 0),
    categoria_id    INTEGER NOT NULL REFERENCES financas_categorias (id) ON UPDATE CASCADE,
    data_vencimento TEXT    NOT NULL,
    data_pagamento  TEXT,                       -- NULL = ainda por pagar/receber
    recorrente      INTEGER NOT NULL DEFAULT 0 CHECK (recorrente IN (0, 1)),
    mes_referencia  TEXT    NOT NULL,           -- 'AAAA-MM': o ciclo mensal a que pertence
    notificado_em   TEXT,                       -- escrito só pelo notificador do Pi (ntfy no dia do vencimento)
    cid             TEXT                        -- id do cliente: POST idempotente (fila offline da PWA)
);
CREATE INDEX financas_lanc_mes ON financas_lancamentos (mes_referencia);
CREATE INDEX financas_lanc_venc ON financas_lancamentos (data_vencimento);
CREATE UNIQUE INDEX financas_lanc_cid ON financas_lancamentos (cid) WHERE cid IS NOT NULL;

-- Meses cuja lista já foi preparada a partir do anterior (evita recopiar
-- quando o utilizador apaga de propósito tudo o que não se aplica).
CREATE TABLE financas_meses (
    mes        TEXT PRIMARY KEY,
    preparado_em TEXT NOT NULL
);
