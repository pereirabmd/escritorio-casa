-- Contas próprias do Pulse (ADR-037): e-mail + password, criadas pelo administrador (sem auto-registo).
-- Tempos em segundos Unix (UTC): sem ambiguidade de fuso.
CREATE TABLE pulse_users (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    email                 TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (length(email) BETWEEN 5 AND 254),
    nome                  TEXT NOT NULL DEFAULT '' CHECK (length(nome) <= 80),
    password_hash         TEXT NOT NULL,
    must_change_password  INTEGER NOT NULL DEFAULT 1 CHECK (must_change_password IN (0, 1)),
    admin                 INTEGER NOT NULL DEFAULT 0 CHECK (admin IN (0, 1)),
    ativo                 INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    falhas                INTEGER NOT NULL DEFAULT 0,
    bloqueado_ate         INTEGER NOT NULL DEFAULT 0,
    criado                INTEGER NOT NULL,
    ultimo_login          INTEGER
);

-- Sessões: só se guarda o hash SHA-256 do token (um vazamento da base não dá sessões válidas).
CREATE TABLE pulse_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    criado      INTEGER NOT NULL,
    ultimo_uso  INTEGER NOT NULL,
    expira      INTEGER NOT NULL,
    dispositivo TEXT NOT NULL DEFAULT '' CHECK (length(dispositivo) <= 120),
    ip          TEXT NOT NULL DEFAULT '',
    cliente     TEXT NOT NULL DEFAULT 'web' CHECK (cliente IN ('web', 'android')),
    revogada    INTEGER NOT NULL DEFAULT 0 CHECK (revogada IN (0, 1))
);
CREATE INDEX pulse_sessions_user ON pulse_sessions (user_id);
