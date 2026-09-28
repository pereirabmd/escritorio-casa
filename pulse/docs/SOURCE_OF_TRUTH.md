# Source of Truth

## Princípio

O Pulse não deve criar várias versões concorrentes do mesmo dado.

Durante a migração, a origem oficial continua a ser a infraestrutura/API do módulo existente.

## Módulos existentes

RTO, Peso, Bilhetes CP, Finanças e Tarefas:
- usar a respetiva API/Core oficial;
- não editar diretamente a BD por fora dessa lógica;
- Pulse é uma interface/consumidor adicional enquanto decorre a migração.

## Depois da migração

RTO, Peso, Bilhetes CP e Finanças:
- Pulse torna-se a interface principal;
- a infraestrutura pode ser consolidada quando apropriado;
- descontinuação só após decisão explícita do utilizador.

Tarefas:
- continua a suportar Pulse + app dedicada.

## Google

Source of truth:
- Gmail -> Google;
- Calendar -> Google;
- Google Tasks, quando usado -> Google.

## Compras

Source of truth:
- Pulse / `pulse.db`.

## Preferências Pulse

Source of truth:
- `pulse.db`.

## Regra de consolidação

A base Pulse pode guardar snapshots/índices/contexto quando necessário, mas isso não torna automaticamente a cópia consolidada na fonte oficial do dado original.
