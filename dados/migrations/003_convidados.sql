-- App convidados (lista do casamento). Vinha de Sheets "Convidados" (A:I) e "Config" (listas Fase/Estado).
-- A identidade passa de "número da linha da folha" para um id estável (AUTOINCREMENT, nunca reutilizado):
-- acabam o deleteDimension e a contabilidade de linhas que se deslocam quando se apaga uma.
CREATE TABLE convidados_lista (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT    NOT NULL CHECK (length(trim(nome)) > 0),
    pessoas      INTEGER NOT NULL DEFAULT 0 CHECK (pessoas >= 0),
    confirmados  INTEGER NOT NULL DEFAULT 0 CHECK (confirmados >= 0),
    fase         TEXT    NOT NULL DEFAULT '',
    estado       TEXT    NOT NULL DEFAULT '',
    notas        TEXT    NOT NULL DEFAULT '',
    mesa         TEXT    NOT NULL DEFAULT '' CHECK (mesa IN ('', '1', '2', '3', '4', '5', '6', '7', '8', '9', '10')),
    telefone     TEXT    NOT NULL DEFAULT '',
    data_convite TEXT    NOT NULL DEFAULT '' CHECK (data_convite = '' OR data_convite GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]'),
    -- linha da folha de onde veio (só nos importados; NULL nos criados na app): torna a importação repetível
    linha_origem INTEGER UNIQUE
);

-- Listas configuráveis (menus Fase e Estado), com a ordem em que aparecem.
CREATE TABLE convidados_opcoes (
    tipo    TEXT    NOT NULL CHECK (tipo IN ('fase', 'estado')),
    posicao INTEGER NOT NULL,
    valor   TEXT    NOT NULL CHECK (length(trim(valor)) > 0),
    PRIMARY KEY (tipo, posicao),
    UNIQUE (tipo, valor)
) WITHOUT ROWID;
