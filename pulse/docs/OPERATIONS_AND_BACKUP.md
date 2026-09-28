# Operações e backups

## Raspberry Pi

O Raspberry Pi aloja:

- backend;
- Web;
- base `pulse.db`;
- jobs;
- downloads do APK;
- logs.

## Backups

Já existe infraestrutura de backup no Raspberry Pi.

Obrigação do Claude Code ao criar `pulse.db`:

1. localizar/verificar configuração atual de backup;
2. confirmar se `pulse.db` está coberta;
3. se não estiver, incluir;
4. documentar a alteração;
5. testar que o ficheiro é efetivamente copiado;
6. não incluir `teste-pulse.db` como backup de produção salvo necessidade explícita.

## Restauro

Deve existir procedimento documentado para restaurar:

- `pulse.db`;
- configuração necessária;
- serviços.

## Logs

Local sugerido:

```text
/var/log/pulse/
```

Separar:
- API;
- worker;
- Web;
- updates.

## Releases

Código:

```text
/opt/pulse/releases/<versão>/
```

Symlink:

```text
/opt/pulse/current
```

Permitir rollback de código sem rollback automático de dados.

## Web

Publicação:
`https://bmdpereira.duckdns.org/pulse/`

## APK

Fora da Play Store.

Manifesto interno deve permitir:
- versão atual;
- version code;
- versão mínima;
- changelog;
- URL APK;
- nível de obrigatoriedade.

## Health

Prever:
- `/health`;
- estado DB;
- serviços Google;
- APIs dos módulos;
- FCM;
- jobs essenciais.

## Modo degradado

Quando um serviço falha:
- manter módulos independentes;
- mostrar alerta;
- não bloquear o produto completo.
