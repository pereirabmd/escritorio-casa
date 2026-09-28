# Estrutura do projeto

## Máquina de desenvolvimento / repositório GitHub

```text
pulse/
├── README.md
├── CLAUDE.md
├── .gitignore
├── .env.example
│
├── docs/
│   ├── SCOPE.md
│   ├── ARCHITECTURE.md
│   ├── DESIGN_SYSTEM.md
│   ├── FOLDER_STRUCTURE.md
│   ├── EXECUTION_PLAN.md
│   ├── DATA_AND_SYNC.md
│   ├── INTEGRATIONS.md
│   ├── AUTH_AND_SECURITY.md
│   ├── AI_SPEC.md
│   ├── API_CONTRACT.md
│   ├── SETTINGS_ADMIN.md
│   ├── TESTING_STRATEGY.md
│   ├── MIGRATION_AND_PARITY.md
│   ├── OPERATIONS_AND_BACKUP.md
│   ├── MODULE_CONTRACTS.md
│   ├── SOURCE_OF_TRUTH.md
│   └── DECISIONS.md
│
├── android/
├── web/
├── server/
├── shared/
│   ├── contracts/
│   ├── schemas/
│   ├── openapi/
│   └── assets/
│
├── assets/
│   ├── branding/
│   │   ├── pulse-icon.png
│   │   └── pulse-loading.webp
│   └── icons/
│
├── scripts/
│   ├── build/
│   ├── deploy/
│   ├── database/
│   └── release/
│
├── infra/
│   ├── nginx/
│   ├── systemd/
│   ├── backup/
│   └── raspberrypi/
│
└── tests/
    ├── e2e/
    ├── contracts/
    └── migration/
```

O repositório contém código e infraestrutura declarativa, não bases de produção.

## Raspberry Pi

Código/releases:

```text
/opt/pulse/
├── releases/
│   ├── beta_YYYYMMDD_X/
│   └── ...
├── current -> releases/<versão-atual>/
├── server/
├── web/
└── scripts/
```

Dados:

```text
/var/lib/pulse/
├── pulse.db
├── uploads/
├── cache/
└── runtime/
```

Testes:

```text
/var/lib/pulse-test/
├── teste-pulse.db
├── teste-<bd-existente-1>.db
└── teste-<bd-existente-2>.db
```

Logs:

```text
/var/log/pulse/
├── api.log
├── worker.log
├── web.log
└── update.log
```

Web publicada:

```text
/var/www/pulse/
```

Downloads/releases APK:

```text
/var/www/pulse-downloads/
├── manifest.json
├── pulse-beta_YYYYMMDD_X.apk
└── changelog/
```

## GitHub

Fluxo:

```text
Máquina desenvolvimento
        |
      git push
        v
      GitHub
        |
   deploy/git pull
        v
   Raspberry Pi
```

## Regra de dados

- Nenhum `.db` de produção entra no GitHub.
- `pulse.db` deve estar em backup.
- `teste-pulse.db` pode ser recriada e não necessita de backup de produção.
