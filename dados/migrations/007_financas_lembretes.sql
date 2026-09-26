-- Lembretes agendados pelo utilizador (avisos ntfy únicos ou mensais), independentes dos vencimentos.
-- Enviados por financas_notificar.py. `data` é o dia do aviso (única) ou o dia de início/dia do mês (mensal;
-- em meses mais curtos avisa no último dia). `ultimo_aviso` = dia (AAAA-MM-DD) do último aviso enviado.
CREATE TABLE financas_lembretes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo       TEXT NOT NULL CHECK (length(trim(titulo)) BETWEEN 1 AND 100),
    nota         TEXT NOT NULL DEFAULT '' CHECK (length(nota) <= 300),
    data         TEXT NOT NULL CHECK (data GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    hora         TEXT NOT NULL CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]'),
    repeticao    TEXT NOT NULL CHECK (repeticao IN ('unica', 'mensal')),
    ativo        INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1)),
    ultimo_aviso TEXT
);
