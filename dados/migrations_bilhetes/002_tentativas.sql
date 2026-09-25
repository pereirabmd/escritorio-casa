-- Uma linha por PEDIDO À CP feito durante uma compra (retenção do lugar, POST /sale, mudança de lugar, desconto do passe...).
-- Escrito só pelo Pi (`bilhetes_cp/scripts/hot_buy.py`), em bloco no fim de cada compra (nunca no caminho crítico) e podado a
-- 90 dias. Serve para analisar o timing (hora real do envio, ligação nova ou reutilizada, quanto demorou, o que a CP respondeu).
-- Diferente de `bilhetes_logs`, que só tem o desfecho de cada compra.
CREATE TABLE bilhetes_tentativas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT    NOT NULL,                       -- hora local do envio, ISO com milissegundos
    data_viagem   TEXT    NOT NULL,
    perna         TEXT    NOT NULL,                       -- 'v102', 'pedido100'...
    comboio       INTEGER,
    fase          TEXT    NOT NULL CHECK (fase IN ('retencao', 'venda', 'lugar', 'desconto')),
    http          INTEGER,                                -- estado HTTP (NULL = sem resposta)
    resultado     TEXT    NOT NULL DEFAULT '',            -- ok | sold_out | not_open | recusado | transient | erro | 429...
    rel_t_ms      INTEGER,                                -- envio relativo a T (ms); NULL se a tentativa não tem T
    rtt_ms        INTEGER,                                -- envio → resposta (ms)
    ligacao_nova  INTEGER CHECK (ligacao_nova IS NULL OR ligacao_nova IN (0, 1)),   -- 1 = abriu uma ligação nova (≈ +250 ms)
    ts_cp         TEXT    NOT NULL DEFAULT '',            -- `timestamp` devolvido pela CP (hora do servidor)
    codigo        TEXT    NOT NULL DEFAULT '',            -- código de erro da CP (ex. WS:RES:114, SIV:DIS:I:302)
    detalhe       TEXT    NOT NULL DEFAULT '',
    gravado       TEXT    NOT NULL DEFAULT (datetime('now'))   -- quando se gravou (UTC): a poda dos 90 dias usa isto, não `ts`
);
CREATE INDEX bilhetes_tentativas_viagem ON bilhetes_tentativas (data_viagem, perna, id);
