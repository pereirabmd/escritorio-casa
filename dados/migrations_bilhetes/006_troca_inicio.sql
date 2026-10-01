-- Troca de bilhete (ADR-083/086): a partir de quando o Pi começa a tentar a troca. Hora local 'AAAA-MM-DDTHH:MM'; vazio = logo que a troca é ativada
-- (o comportamento de sempre). O fim continua a ser `troca_antecedencia_min` minutos antes da partida. «Tentar agora» ignora o início.
ALTER TABLE bilhetes_pedidos ADD COLUMN troca_inicio TEXT NOT NULL DEFAULT '';
