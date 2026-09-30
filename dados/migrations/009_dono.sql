-- Peso e RTO passam a ter dono (ADR-063): cada pessoa vê e escreve só o que é seu. `dono` é o e-mail da conta (o mesmo que o Pulse envia
-- em X-Pulse-User). O que já existe fica com dono '' e o serviço atribui-o ao dono inicial no arranque (db.adotar_orfaos).
ALTER TABLE peso_registos ADD COLUMN dono TEXT NOT NULL DEFAULT '';
CREATE INDEX peso_registos_dono ON peso_registos (dono, quando);

CREATE TABLE peso_config_novo (
    dono  TEXT NOT NULL DEFAULT '',
    chave TEXT NOT NULL,
    valor TEXT NOT NULL,
    PRIMARY KEY (dono, chave)
);
INSERT INTO peso_config_novo (dono, chave, valor) SELECT '', chave, valor FROM peso_config;
DROP TABLE peso_config;
ALTER TABLE peso_config_novo RENAME TO peso_config;

CREATE TABLE rto_dias_novo (
    dono  TEXT NOT NULL DEFAULT '',
    data  TEXT NOT NULL CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    marca TEXT NOT NULL CHECK (marca IN ('T', 'C')),
    PRIMARY KEY (dono, data)
) WITHOUT ROWID;
INSERT INTO rto_dias_novo (dono, data, marca) SELECT '', data, marca FROM rto_dias;
DROP TABLE rto_dias;
ALTER TABLE rto_dias_novo RENAME TO rto_dias;

ALTER TABLE rto_notas ADD COLUMN dono TEXT NOT NULL DEFAULT '';
CREATE INDEX rto_notas_dono ON rto_notas (dono, data_inicio);
