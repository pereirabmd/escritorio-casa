-- Contas Google ligadas ao Pulse (ADR-049): Gmail e Calendar. O login do Pulse é separado (ADR-037).
-- O refresh token vive só aqui, cifrado (Fernet) com a chave do servidor; nunca sai para a Web nem para o Android.

CREATE TABLE google_accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    email         TEXT NOT NULL COLLATE NOCASE CHECK (length(email) BETWEEN 3 AND 254),
    nome          TEXT NOT NULL DEFAULT '' CHECK (length(nome) <= 120),
    refresh_token TEXT NOT NULL,                                                   -- cifrado
    servicos      TEXT NOT NULL DEFAULT '' CHECK (servicos GLOB '[a-z,]*' OR servicos = ''),   -- os que o Google concedeu: «gmail», «calendar»
    estado        TEXT NOT NULL DEFAULT 'ok' CHECK (estado IN ('ok', 'reautorizar')),
    criado        INTEGER NOT NULL,
    atualizado    INTEGER NOT NULL,
    UNIQUE (user_id, email)
);

-- Passo intermédio do OAuth: um só uso, dura 10 minutos. Liga o regresso do Google ao utilizador que o pediu (contra CSRF).
CREATE TABLE google_oauth_states (
    state         TEXT PRIMARY KEY CHECK (length(state) BETWEEN 20 AND 100),
    user_id       INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    servicos      TEXT NOT NULL,
    code_verifier TEXT NOT NULL,                                                   -- PKCE
    criado        INTEGER NOT NULL
);
