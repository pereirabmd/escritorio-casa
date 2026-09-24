-- BD separada `bilhetes.db` (decisão: a compra com hora certa nunca espera por um lock de outra app).
-- Vinha do Google Sheets (abas Config, Bilhetes, Logs, Pedidos). Estas tabelas são lidas/escritas por DOIS
-- lados: o Raspberry Pi (scheduler, hot_buy, pedidos.py, live_delay — `bilhetes_cp/scripts/store.py`, SQL
-- direto, sem passar pela API) e a PWA (através de `dados/apps/bilhetes.py`). Alterar aqui = alterar os dois.

-- Passe Ferroviário Verde: uma única linha. A data de expiração e os dias que faltam calculam-se (eram
-- fórmulas na Sheet): expira a data_ultima_compra + validade_dias (29 = 30 dias contando o dia do carregamento).
CREATE TABLE bilhetes_passe (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    data_ultima_compra  TEXT CHECK (data_ultima_compra IS NULL OR data_ultima_compra GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    validade_dias       INTEGER NOT NULL DEFAULT 29 CHECK (validade_dias BETWEEN 1 AND 366)
);
INSERT INTO bilhetes_passe (id, data_ultima_compra, validade_dias) VALUES (1, NULL, 29);

-- Config semanal: uma linha = uma viagem (sem par ida/volta). O `id` É o número da viagem no sistema
-- ('v<id>' — parte da chave do lock de compra), por isso é estável e nunca reutilizado. Os ids importados
-- da Sheet mantêm o número da linha (12 continua 'v12'); as novas começam em 100, longe de qualquer lock antigo.
CREATE TABLE bilhetes_viagens (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    data     TEXT    NOT NULL CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    origem   TEXT    NOT NULL CHECK (length(trim(origem)) BETWEEN 1 AND 60),
    destino  TEXT    NOT NULL CHECK (length(trim(destino)) BETWEEN 1 AND 60),
    comboio  INTEGER NOT NULL CHECK (comboio > 0),
    hora     TEXT    NOT NULL CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]'),
    ativo    TEXT    NOT NULL DEFAULT 'SIM' CHECK (ativo IN ('SIM', 'NAO'))
);
CREATE INDEX bilhetes_viagens_data ON bilhetes_viagens (data);

-- Bilhetes comprados (escritos só pelo Pi, depois de uma compra confirmada).
CREATE TABLE bilhetes_compras (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    data          TEXT NOT NULL,
    comboio       INTEGER,
    origem        TEXT NOT NULL DEFAULT '',
    destino       TEXT NOT NULL DEFAULT '',
    hora_partida  TEXT NOT NULL DEFAULT '',
    carruagem     TEXT NOT NULL DEFAULT '',
    lugar         TEXT NOT NULL DEFAULT '',
    referencia    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX bilhetes_compras_data ON bilhetes_compras (data);
-- a mesma compra nunca entra duas vezes (o Pi pode repetir a escrita após uma falha)
CREATE UNIQUE INDEX bilhetes_compras_ref ON bilhetes_compras (referencia) WHERE referencia <> '';

-- Registo de execução para a aba "Registo" da PWA: só eventos com resultado (uma linha por perna e marco),
-- NUNCA cada tentativa da rajada do esgotado — essas ficam só em logs/hot_buy.log no Pi.
CREATE TABLE bilhetes_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    tipo          TEXT NOT NULL DEFAULT '',
    data_viagem   TEXT NOT NULL DEFAULT '',
    perna         TEXT NOT NULL DEFAULT '',
    comboio       TEXT NOT NULL DEFAULT '',
    status_http   TEXT NOT NULL DEFAULT '',
    resultado     TEXT NOT NULL DEFAULT '',
    referencia    TEXT NOT NULL DEFAULT '',
    mensagem_erro TEXT NOT NULL DEFAULT ''
);
CREATE INDEX bilhetes_logs_ts ON bilhetes_logs (ts);

-- Pedidos avulsos (3.2.1): viagens da Config que esgotaram o retry, espelhadas pelo Pi. `retry`,
-- `intervalo_minutos` e `forcar` são escritos pela PWA; o resto só pelo Pi. O `id` é o 'pedido<id>'.
CREATE TABLE bilhetes_pedidos (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    data               TEXT    NOT NULL,
    origem             TEXT    NOT NULL DEFAULT '',
    destino            TEXT    NOT NULL DEFAULT '',
    comboio            INTEGER,
    hora               TEXT    NOT NULL DEFAULT '',
    ativo              TEXT    NOT NULL DEFAULT 'SIM' CHECK (ativo IN ('SIM', 'NAO')),
    retry              TEXT    NOT NULL DEFAULT 'NAO' CHECK (retry IN ('SIM', 'NAO')),
    intervalo_minutos  INTEGER CHECK (intervalo_minutos IS NULL OR intervalo_minutos BETWEEN 1 AND 1440),
    forcar             TEXT    NOT NULL DEFAULT 'NAO' CHECK (forcar IN ('SIM', 'NAO')),
    estado             TEXT    NOT NULL DEFAULT 'PENDENTE',
    ultima_tentativa   TEXT    NOT NULL DEFAULT '',
    referencia         TEXT    NOT NULL DEFAULT '',
    mensagem           TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX bilhetes_pedidos_data ON bilhetes_pedidos (data);

-- Os ids novos de viagens e pedidos começam em 100 (ver acima).
INSERT INTO sqlite_sequence (name, seq) VALUES ('bilhetes_viagens', 99), ('bilhetes_pedidos', 99);
