-- Tipo de documento do passageiro (ADR-071): a CP pede-o no passo do passageiro. CC = Cartão de Cidadão (o que sempre se enviou),
-- AR = Autorização de Residência (o perfil da CP mostra-o com este código). As pessoas que já existem ficam CC.
ALTER TABLE bilhetes_utilizadores ADD COLUMN passageiro_tipo_doc TEXT NOT NULL DEFAULT 'CC' CHECK (passageiro_tipo_doc IN ('CC', 'AR'));
