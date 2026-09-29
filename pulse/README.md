# Pulse

Pulse é uma aplicação pessoal agregadora, com APK Android e interface Web responsiva, apoiada por um backend no Raspberry Pi.

O objetivo é concentrar num único produto, com aparência profissional e coerente, as funcionalidades de:

- Gmail multi-conta;
- Google Calendar;
- Tarefas;
- Bilhetes CP;
- Peso;
- RTO;
- Finanças;
- Lista de Compras.

**Estado (29/09/2026)**: na Web estão completos Tarefas, Peso, RTO, Finanças, Bilhetes CP e Compras (paridade em `docs/PARITY_*.md`); faltam Gmail e Google Calendar, e a app Android. Os módulos podem ser desativados pelo administrador (Definições → Administração).

O dashboard **Hoje** apresenta apenas as funcionalidades essenciais e imediatas de cada módulo. As funcionalidades completas ficam em **Mais**.

## Plataformas

- Android nativo: Kotlin + Jetpack Compose + Material 3.
- Web: React + Vite + TypeScript.
- Backend: Python + FastAPI no Raspberry Pi.
- Base própria do Pulse: SQLite (`pulse.db`).
- Base de teste: `teste-pulse.db`.
- GitHub: código, documentação, scripts, contratos e assets; nunca bases de produção.

## Acessos

- Web autenticada: `https://bmdpereira.duckdns.org/pulse/`
- Página pública/referência da aplicação: `https://pereirabmd.github.io/escritorio-casa/index.html`

## Princípios

1. Aparência profissional, moderna, limpa e consistente.
2. Português de Portugal (`pt-PT`) como idioma canónico.
3. Infraestrutura partilhada sempre que possível.
4. Escritas sempre através das APIs/serviços oficiais.
5. Offline-first no Android, com fila persistente.
6. Migração com paridade funcional antes da descontinuação das apps dedicadas.
7. IA preparada para consultar e executar ações de forma controlada.
8. Testes usam exclusivamente bases `teste-*`.
