-- Horário escolar (aba "Horário" da app tarefas + aviso 30 min antes de acabar a última aula do dia).
-- Uma linha por aula. Duas linhas no mesmo dia e hora NÃO são erro: é a turma dividida em dois turnos
-- (ex.: C.D. e TIC), e ambas contam (para a última aula do dia usa-se a hora de fim mais tarde de todas).
-- Lido pela PWA (API, apps/tarefas.py) e pelo Pi (tarefas/pi/horario.py, SQL direto via store.py).

CREATE TABLE tarefas_horario (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    aluno        TEXT NOT NULL CHECK (length(trim(aluno)) BETWEEN 1 AND 60),
    ano_letivo   TEXT NOT NULL CHECK (ano_letivo GLOB '[0-9][0-9][0-9][0-9]/[0-9][0-9][0-9][0-9]'),
    dia_semana   INTEGER NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),   -- ISO: 1 = 2ª feira ... 7 = domingo
    hora_inicio  TEXT NOT NULL CHECK (hora_inicio GLOB '[0-2][0-9]:[0-5][0-9]'),
    hora_fim     TEXT NOT NULL CHECK (hora_fim GLOB '[0-2][0-9]:[0-5][0-9]' AND hora_fim > hora_inicio),
    disciplina   TEXT NOT NULL CHECK (length(trim(disciplina)) BETWEEN 1 AND 80),
    sala         TEXT NOT NULL DEFAULT '',
    UNIQUE (aluno, ano_letivo, dia_semana, hora_inicio, disciplina, sala)   -- tornar a importação idempotente
);
CREATE INDEX tarefas_horario_dia ON tarefas_horario (ano_letivo, dia_semana, hora_inicio);
