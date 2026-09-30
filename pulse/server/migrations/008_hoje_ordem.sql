-- Ordem dos cartões do «Hoje» por utilizador (ADR-054): lista JSON de ids de módulos, igual no APK e na Web.
CREATE TABLE pulse_hoje_ordem (
    user_id  INTEGER PRIMARY KEY REFERENCES pulse_users (id) ON DELETE CASCADE,
    ordem    TEXT NOT NULL DEFAULT '[]'
);
