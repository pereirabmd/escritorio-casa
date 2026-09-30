-- Compras: «Última chamada» (ADR-076). Uma só por lista partilhada e por ida às compras: há linha = já foi feita.
-- Apaga-se com «Limpar comprados» (fim da ida às compras) e caduca sozinha ao fim de 12 h (regra no serviço).
CREATE TABLE shop_last_call (
    list_id  INTEGER PRIMARY KEY REFERENCES shop_lists (id) ON DELETE CASCADE,
    user_id  INTEGER REFERENCES pulse_users (id) ON DELETE SET NULL,
    mensagem TEXT NOT NULL DEFAULT '' CHECK (length(mensagem) <= 120),
    criado   INTEGER NOT NULL
);
