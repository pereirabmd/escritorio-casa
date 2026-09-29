-- Notificações do Pulse (ADR-044): dispositivos Android com token FCM e uma caixa de saída de eventos.
-- Os eventos vêm das apps de origem (ex.: bilhetes_cp, que continua a avisar por ntfy) ou do próprio Pulse; cada evento é
-- guardado uma vez (idempotente por `chave`) e entregue por todos os canais ligados. Sem canal FCM configurado, ficam na
-- caixa (consultável em GET /notifications) — nada se perde e o Android pode ir buscá-los.

CREATE TABLE pulse_devices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    fcm_token   TEXT NOT NULL UNIQUE CHECK (length(fcm_token) BETWEEN 20 AND 4096),
    plataforma  TEXT NOT NULL DEFAULT 'android' CHECK (plataforma IN ('android', 'web')),
    nome        TEXT NOT NULL DEFAULT '' CHECK (length(nome) <= 80),
    criado      INTEGER NOT NULL,
    ultimo_uso  INTEGER NOT NULL,
    ativo       INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);
CREATE INDEX pulse_devices_user ON pulse_devices (user_id);

CREATE TABLE pulse_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    criado      INTEGER NOT NULL,
    modulo      TEXT NOT NULL CHECK (length(modulo) BETWEEN 1 AND 40),
    tipo        TEXT NOT NULL CHECK (length(tipo) BETWEEN 1 AND 60),
    titulo      TEXT NOT NULL CHECK (length(titulo) BETWEEN 1 AND 200),
    corpo       TEXT NOT NULL DEFAULT '' CHECK (length(corpo) <= 1000),
    dados       TEXT NOT NULL DEFAULT '{}' CHECK (length(dados) <= 2000),          -- JSON com strings (deep link, tags…)
    chave       TEXT UNIQUE CHECK (chave IS NULL OR length(chave) BETWEEN 8 AND 80),   -- idempotência: o mesmo aviso não entra duas vezes
    entregar_em INTEGER,                                                                -- segundos Unix; NULL = já. O FCM não agenda: é o Pulse que espera (ADR-032)
    estado      TEXT NOT NULL DEFAULT 'novo' CHECK (estado IN ('agendado', 'novo', 'enviado', 'sem_canal', 'erro')),
    tentativas  INTEGER NOT NULL DEFAULT 0,
    entregue_em INTEGER,
    lido        INTEGER NOT NULL DEFAULT 0 CHECK (lido IN (0, 1))
);
CREATE INDEX pulse_events_user ON pulse_events (user_id, id DESC);
CREATE INDEX pulse_events_agendados ON pulse_events (entregar_em) WHERE estado = 'agendado';
