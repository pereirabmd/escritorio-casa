-- Bilhetes CP: comboios favoritos (ADR-078). Dados do próprio Pulse, por conta: preenchem o seletor «Favoritos» do editor da semana e
-- permitem marcar uma viagem de uma vez (por voz, «marca o comboio da manhã amanhã»). Não tocam na base dos Bilhetes.
CREATE TABLE bilhetes_favoritos (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    apelido  TEXT NOT NULL DEFAULT '' CHECK (length(apelido) <= 40),                    -- «Manhã para Lisboa» (opcional; serve para o nomear por voz)
    comboio  INTEGER NOT NULL CHECK (comboio BETWEEN 1 AND 99999),
    hora     TEXT NOT NULL CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]'),
    origem   TEXT NOT NULL CHECK (length(trim(origem)) BETWEEN 1 AND 60),
    destino  TEXT NOT NULL CHECK (length(trim(destino)) BETWEEN 1 AND 60),
    criado   INTEGER NOT NULL,
    UNIQUE (user_id, comboio, hora, origem, destino)
);
CREATE INDEX bilhetes_favoritos_user ON bilhetes_favoritos (user_id);
