-- Acesso por pessoa e «Hoje» por pessoa (ADR-063).
-- Os módulos a que cada conta tem acesso. As contas que já existem ficam com todos (comportamento de hoje); uma conta nova
-- só tem o que o administrador lhe der.
CREATE TABLE pulse_user_modulos (
    user_id INTEGER NOT NULL REFERENCES pulse_users (id) ON DELETE CASCADE,
    modulo  TEXT NOT NULL CHECK (length(modulo) BETWEEN 1 AND 40),
    PRIMARY KEY (user_id, modulo)
) WITHOUT ROWID;
INSERT INTO pulse_user_modulos (user_id, modulo)
    SELECT u.id, m.modulo FROM pulse_users u CROSS JOIN (
        SELECT 'tarefas' AS modulo UNION ALL SELECT 'bilhetes' UNION ALL SELECT 'rto' UNION ALL SELECT 'peso' UNION ALL SELECT 'financas'
        UNION ALL SELECT 'compras' UNION ALL SELECT 'calendario' UNION ALL SELECT 'email') m;

-- Os cartões do Hoje que a pessoa escondeu (lista JSON de ids); além da ordem, já guardada por pessoa.
ALTER TABLE pulse_hoje_ordem ADD COLUMN ocultos TEXT NOT NULL DEFAULT '[]';
