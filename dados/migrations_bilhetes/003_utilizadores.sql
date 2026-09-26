-- Vários utilizadores (Bruno, Camila, Bruninho, Davi): fase 1 = só o modelo de dados e a página de administração.
-- Os scripts de compra do Pi continuam, por agora, a usar as credenciais do .env (um único utilizador): esta tabela
-- guarda os dados para a fase 2 (scripts por utilizador). NÃO há coluna de ntfy (fica de fora, decisão de 26/09/2026).
--
-- Segredos: `cp_password_enc` é cifrada com Fernet (chave BILHETES_FERNET_KEY, só no .env do Pi; NUNCA vai para a BD
-- nem para o Git). Sem a chave as passwords são irrecuperáveis: voltam a introduzir-se na página de administração.
CREATE TABLE bilhetes_utilizadores (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    nome                     TEXT    NOT NULL UNIQUE COLLATE NOCASE CHECK (length(trim(nome)) BETWEEN 1 AND 40),
    email                    TEXT    UNIQUE COLLATE NOCASE CHECK (email IS NULL OR (length(email) BETWEEN 3 AND 120 AND instr(email, '@') > 1)),
                                     -- e-mail Google com que entra na PWA; NULL = ainda não tem login próprio (só o admin marca por ele)
    admin                    INTEGER NOT NULL DEFAULT 0 CHECK (admin IN (0, 1)),
    ativo                    INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    -- conta na CP (login em login.cp.pt)
    cp_email                 TEXT    NOT NULL DEFAULT '',
    cp_password_enc          TEXT    NOT NULL DEFAULT '',
    -- dados do passageiro e da faturação enviados na compra
    passageiro_nome          TEXT    NOT NULL DEFAULT '',
    passageiro_cc            TEXT    NOT NULL DEFAULT '',     -- nº do Cartão de Cidadão
    passageiro_telemovel     TEXT    NOT NULL DEFAULT '',
    nif                      TEXT    NOT NULL DEFAULT '',
    -- Passe Ferroviário Verde
    passe_verde_numero       TEXT    NOT NULL DEFAULT '',
    passe_data_ultima_compra TEXT    CHECK (passe_data_ultima_compra IS NULL OR passe_data_ultima_compra GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    passe_validade_dias      INTEGER NOT NULL DEFAULT 29 CHECK (passe_validade_dias BETWEEN 1 AND 366)
);

-- O Bruno é o utilizador 1 e administrador; o passe dele vem da tabela atual. As credenciais entram pela página de
-- administração (ou por `bilhetes_utilizadores.py importar-env`), nunca por SQL.
INSERT INTO bilhetes_utilizadores (id, nome, email, admin, passe_data_ultima_compra, passe_validade_dias)
SELECT 1, 'Bruno', 'pereirabmd@gmail.com', 1, data_ultima_compra, validade_dias FROM bilhetes_passe WHERE id = 1;

-- Enquanto os scripts/API ainda escrevem o passe em `bilhetes_passe`, o do Bruno espelha-se aqui.
CREATE TRIGGER bilhetes_passe_espelho AFTER UPDATE ON bilhetes_passe
BEGIN
    UPDATE bilhetes_utilizadores SET passe_data_ultima_compra = NEW.data_ultima_compra, passe_validade_dias = NEW.validade_dias WHERE id = 1;
END;

-- Cada viagem, compra, pedido e registo passa a ter dono. Os que já existem (e o que os scripts ainda gravam sem
-- indicar o dono) ficam do utilizador 1. Não se usa REFERENCES no ADD COLUMN (o SQLite exige DEFAULT NULL com chaves
-- estrangeiras ligadas): a integridade é garantida pelos gatilhos abaixo. Os ids das viagens/pedidos não mudam
-- ('v<id>' faz parte da chave do lock de compra).
ALTER TABLE bilhetes_viagens ADD COLUMN utilizador_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE bilhetes_pedidos ADD COLUMN utilizador_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE bilhetes_compras ADD COLUMN utilizador_id INTEGER NOT NULL DEFAULT 1;
ALTER TABLE bilhetes_logs    ADD COLUMN utilizador_id INTEGER NOT NULL DEFAULT 1;
CREATE INDEX bilhetes_viagens_util ON bilhetes_viagens (utilizador_id, data);
CREATE INDEX bilhetes_pedidos_util ON bilhetes_pedidos (utilizador_id, data);
CREATE INDEX bilhetes_compras_util ON bilhetes_compras (utilizador_id, data);

CREATE TRIGGER bilhetes_viagens_dono_i BEFORE INSERT ON bilhetes_viagens
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
CREATE TRIGGER bilhetes_viagens_dono_u BEFORE UPDATE OF utilizador_id ON bilhetes_viagens
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
CREATE TRIGGER bilhetes_pedidos_dono_i BEFORE INSERT ON bilhetes_pedidos
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
CREATE TRIGGER bilhetes_pedidos_dono_u BEFORE UPDATE OF utilizador_id ON bilhetes_pedidos
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
CREATE TRIGGER bilhetes_compras_dono_i BEFORE INSERT ON bilhetes_compras
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
CREATE TRIGGER bilhetes_compras_dono_u BEFORE UPDATE OF utilizador_id ON bilhetes_compras
WHEN NOT EXISTS (SELECT 1 FROM bilhetes_utilizadores WHERE id = NEW.utilizador_id)
BEGIN SELECT RAISE(ABORT, 'utilizador inexistente'); END;
-- (os registos não levam gatilho de inserção: um log nunca deve falhar por causa do dono — nada falha em silêncio)

-- Um utilizador com dados não se apaga (desativa-se); o utilizador 1 nunca se apaga.
CREATE TRIGGER bilhetes_utilizadores_apagar BEFORE DELETE ON bilhetes_utilizadores
WHEN OLD.id = 1
   OR EXISTS (SELECT 1 FROM bilhetes_viagens WHERE utilizador_id = OLD.id)
   OR EXISTS (SELECT 1 FROM bilhetes_pedidos WHERE utilizador_id = OLD.id)
   OR EXISTS (SELECT 1 FROM bilhetes_compras WHERE utilizador_id = OLD.id)
BEGIN SELECT RAISE(ABORT, 'utilizador com dados: desativa em vez de apagar'); END;
