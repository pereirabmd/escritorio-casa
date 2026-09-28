-- Base do pulse.db: só dados próprios do Pulse (ver docs/DATA_AND_SYNC.md). Nada aqui duplica dados das apps de origem.

-- Preferências e configuração do Pulse (chave/valor).
CREATE TABLE pulse_settings (
    chave       TEXT PRIMARY KEY CHECK (length(chave) BETWEEN 1 AND 80),
    valor       TEXT NOT NULL DEFAULT '',
    atualizado  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime'))
);

-- Centro de atividade (retenção de 30 dias, limpeza automática): o que foi feito, por quem e com que resultado.
-- `origem` distingue a interface da IA (ações da IA são auditadas, AI_SPEC).
CREATE TABLE pulse_activity (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%d %H:%M:%S', 'now', 'localtime')),
    utilizador TEXT NOT NULL,
    modulo     TEXT NOT NULL,
    acao       TEXT NOT NULL,
    origem     TEXT NOT NULL DEFAULT 'ui' CHECK (origem IN ('ui', 'ia', 'sistema')),
    resultado  TEXT NOT NULL DEFAULT 'ok' CHECK (resultado IN ('ok', 'erro', 'pendente')),
    detalhe    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX pulse_activity_ts ON pulse_activity (ts);
