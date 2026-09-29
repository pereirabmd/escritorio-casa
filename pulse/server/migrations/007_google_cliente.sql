-- O pedido de ligação Google diz de que cliente veio (ADR-051): a Web regressa às Definições; a app Android regressa ao `pulse://google`.
ALTER TABLE google_oauth_states ADD COLUMN cliente TEXT NOT NULL DEFAULT 'web' CHECK (cliente IN ('web', 'android'));
