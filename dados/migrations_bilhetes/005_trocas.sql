-- Troca de bilhete (ADR-083): um pedido pode existir para trocar um bilhete por outro comboio (mesma data e sentido). Quando há lugar no comboio
-- novo, o Pi reserva-o, cancela o bilhete antigo (venda `troca_venda` da CP) e só então confirma o novo. Para de tentar `troca_antecedencia_min`
-- minutos antes da partida. Sem `troca_venda` o pedido é um pedido avulso normal.
ALTER TABLE bilhetes_pedidos ADD COLUMN troca_venda INTEGER;
ALTER TABLE bilhetes_pedidos ADD COLUMN troca_referencia TEXT NOT NULL DEFAULT '';
ALTER TABLE bilhetes_pedidos ADD COLUMN troca_antecedencia_min INTEGER NOT NULL DEFAULT 30;
