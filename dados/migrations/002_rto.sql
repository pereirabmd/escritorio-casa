-- App RTO (dias de escritório/casa + notas). Vinha de Sheets "Dados" e "Notas".
-- Modelo esparso: só se guardam os dias com marca (T/C); os outros dias simplesmente
-- não existem. Acaba a "inicialização da folha/do ano" e o índice de linhas do Sheets.
CREATE TABLE rto_dias (
    data  TEXT PRIMARY KEY CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    marca TEXT NOT NULL CHECK (marca IN ('T', 'C'))
) WITHOUT ROWID;

-- Notas: intervalo de datas (ISO) + categoria livre ("Férias", "Astreinte", "Validação"...).
-- A app tolera notas com só uma das datas, por isso ambas são opcionais (mas nunca todos os campos vazios).
-- AUTOINCREMENT: um id nunca é reutilizado, o que permite ao "Desfazer" repor uma nota apagada com o mesmo id.
CREATE TABLE rto_notas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    data_inicio TEXT CHECK (data_inicio IS NULL OR data_inicio GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    data_fim    TEXT CHECK (data_fim IS NULL OR data_fim GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    categoria   TEXT NOT NULL DEFAULT '',
    descricao   TEXT NOT NULL DEFAULT '',
    cid         TEXT,  -- idempotência de importações/criações repetidas (NULL nas notas normais)
    CHECK (data_inicio IS NOT NULL OR data_fim IS NOT NULL OR categoria <> '' OR descricao <> ''),
    CHECK (data_inicio IS NULL OR data_fim IS NULL OR data_fim >= data_inicio)
);
CREATE INDEX rto_notas_inicio ON rto_notas (data_inicio);
CREATE UNIQUE INDEX rto_notas_cid ON rto_notas (cid) WHERE cid IS NOT NULL;
