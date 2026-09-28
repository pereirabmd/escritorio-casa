-- Idempotência das criações vindas de clientes com fila offline (o Pulse no Android): o cliente gera um `cid`
-- (8-64 caracteres [A-Za-z0-9-]) e um POST repetido devolve o que já foi criado em vez de duplicar.
-- Coluna nova e anulável: nenhum INSERT existente (API, Pi, importadores) a nomeia, por isso nada muda para eles.
ALTER TABLE tarefas_tarefas ADD COLUMN cid TEXT;
ALTER TABLE tarefas_instancias ADD COLUMN cid TEXT;
CREATE UNIQUE INDEX tarefas_tarefas_cid ON tarefas_tarefas (cid) WHERE cid IS NOT NULL;
CREATE UNIQUE INDEX tarefas_instancias_cid ON tarefas_instancias (cid) WHERE cid IS NOT NULL;
