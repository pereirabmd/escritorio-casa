-- Piloto: app peso (Sheets "Registos" A:C e "Config" B2:B9).
-- Convenção: tabelas prefixadas com o nome da app; datas em texto ISO
-- ('YYYY-MM-DD HH:MM:SS', hora local) — nunca serial do Sheets.
CREATE TABLE peso_registos (
    id     INTEGER PRIMARY KEY,
    quando TEXT    NOT NULL,
    peso   REAL    NOT NULL CHECK (peso > 0),
    nota   TEXT    NOT NULL DEFAULT '',
    -- id gerado pelo cliente: torna o POST idempotente (fila offline/retry
    -- da PWA nunca duplica um registo). NULL para registos importados.
    cid    TEXT
);
CREATE INDEX peso_registos_quando ON peso_registos (quando);
CREATE UNIQUE INDEX peso_registos_cid ON peso_registos (cid) WHERE cid IS NOT NULL;

-- chave/valor: altura, nascimento, sexo, pesoAlvo, atividade, diaControlo, pesoMin, pesoMax
CREATE TABLE peso_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
