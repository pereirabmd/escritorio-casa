# Migração e paridade

## Objetivo

Migrar aplicações dedicadas para o Pulse sem perda funcional.

## Estado dos módulos

### RTO
- primeira vaga;
- preservar todas as funcionalidades;
- app dedicada só é descontinuada quando o utilizador declarar a migração concluída.

### Peso
- primeira vaga;
- mesma regra.

### Bilhetes CP
- primeira vaga;
- mesma regra.

### Tarefas
- primeira vaga;
- app dedicada pode continuar permanentemente;
- existem outros utilizadores que podem não usar o Pulse;
- partilhar infraestrutura/API.

### Finanças
- vaga posterior;
- preservar funcionalidades;
- descontinuação apenas após validação explícita.

### Compras
- nasce no Pulse;
- não existe app dedicada.

## Functional parity

Cada módulo deve manter tabela de paridade:

```text
Funcionalidade | App original | Pulse | Estado | Notas
```

## Evoluções durante migração

Enquanto a app dedicada ainda existir:
- qualquer evolução relevante deve ser migrada para o Pulse;
- ou registada explicitamente no plano de migração.

Não deixar o Pulse divergir silenciosamente.

## Fim da migração

A migração só termina quando o utilizador disser explicitamente que a app está validada.

Não descontinuar automaticamente.
