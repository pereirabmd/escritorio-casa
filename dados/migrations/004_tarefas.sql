-- App tarefas (Tarefas de Casa). Vinha de Sheets: Tarefas, Instancias, Config, Piscina, Auditoria.
-- (LogEnvios e Subscriptions eram do Apps Script/FCM e morreram com ele: não migram.)
-- Lido/escrito por DOIS lados: a PWA (pela API, `apps/tarefas.py`) e o Pi (`tarefas/pi/store.py`, SQL direto:
-- instancias.py, recalcular.py, manutencao.py, servidor.py). Alterar uma tabela = alterar os dois.

CREATE TABLE tarefas_tarefas (
    id               TEXT PRIMARY KEY CHECK (id GLOB 'T[0-9]*'),
    nome             TEXT NOT NULL CHECK (length(trim(nome)) BETWEEN 1 AND 200),
    categoria        TEXT NOT NULL DEFAULT '',
    icone            TEXT NOT NULL DEFAULT '',
    recorrencia      TEXT NOT NULL CHECK (recorrencia IN ('Diaria', 'Semanal', 'Dias especificos', 'Mensal', 'Trimestral', 'Semestral', 'Pontual')),
    -- Semanal/Dias especificos: dias ('Seg,Qua'); Pontual/Trimestral/Semestral: a data ISO (única, ou de início).
    -- Mantém-se a convenção que a PWA e o Pi sempre usaram (reaproveitar esta coluna para a data).
    dias_semana      TEXT NOT NULL DEFAULT '',
    dia_mes          INTEGER CHECK (dia_mes IS NULL OR dia_mes BETWEEN 1 AND 31),
    hora_notificacao TEXT NOT NULL DEFAULT '' CHECK (hora_notificacao = '' OR hora_notificacao GLOB '[0-2][0-9]:[0-5][0-9]'),
    pessoa_padrao    TEXT NOT NULL DEFAULT '',
    ativa            INTEGER NOT NULL DEFAULT 1 CHECK (ativa IN (0, 1)),
    prioridade       TEXT NOT NULL DEFAULT 'Media' CHECK (prioridade IN ('Alta', 'Media', 'Baixa')),
    rotacao_pessoas  TEXT NOT NULL DEFAULT '',   -- 'Bruno,Camila': alterna a cada ocorrência nova
    depende_de       TEXT NOT NULL DEFAULT ''    -- id de outra tarefa: só notifica depois de essa estar Feita hoje
);

CREATE TABLE tarefas_instancias (
    id                   TEXT PRIMARY KEY,
    tarefa_id            TEXT NOT NULL,
    data                 TEXT NOT NULL CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    pessoa               TEXT NOT NULL DEFAULT '',
    estado               TEXT NOT NULL DEFAULT 'Pendente' CHECK (estado IN ('Pendente', 'Feita', 'Saltada', 'Atrasada')),
    data_conclusao       TEXT NOT NULL DEFAULT '' CHECK (data_conclusao = '' OR data_conclusao GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9] [0-9][0-9]:[0-9][0-9]'),
    notificacao_enviada  INTEGER NOT NULL DEFAULT 0 CHECK (notificacao_enviada IN (0, 1)),
    UNIQUE (tarefa_id, data)      -- a chave de idempotência do gerador: nunca duas ocorrências da mesma tarefa no mesmo dia
);
CREATE INDEX tarefas_instancias_data ON tarefas_instancias (data);
CREATE INDEX tarefas_instancias_estado ON tarefas_instancias (estado);

-- Pares chave/valor: Pessoa1_Nome/_Cor/_Email/_NtfyUser/_NtfyPasswordEnc, Categoria1.., HoraPadrao,
-- DiasAntecedenciaGeracao, NaoIncomodarInicio/Fim, PiscinaMesInicioQuente/FimQuente...
CREATE TABLE tarefas_config (
    chave  TEXT PRIMARY KEY CHECK (chave GLOB '[A-Za-z]*' AND length(chave) <= 80),
    valor  TEXT NOT NULL DEFAULT '',
    notas  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE tarefas_piscina (
    id                    TEXT PRIMARY KEY,
    nome                  TEXT NOT NULL,
    aviso_longo           INTEGER NOT NULL DEFAULT 0 CHECK (aviso_longo IN (0, 1)),
    ultima_data           TEXT CHECK (ultima_data IS NULL OR ultima_data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    proxima_data          TEXT CHECK (proxima_data IS NULL OR proxima_data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    notificacao_enviada   INTEGER NOT NULL DEFAULT 0 CHECK (notificacao_enviada IN (0, 1)),
    usar_intervalo_longo  INTEGER NOT NULL DEFAULT 0 CHECK (usar_intervalo_longo IN (0, 1))
);

-- Quem fez o quê (a lista "Auditoria" da app): escrita pela PWA e por nada mais.
CREATE TABLE tarefas_auditoria (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    acao         TEXT NOT NULL DEFAULT '',
    tarefa       TEXT NOT NULL DEFAULT '',
    pessoa       TEXT NOT NULL DEFAULT '',
    instancia_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX tarefas_auditoria_ts ON tarefas_auditoria (ts);
