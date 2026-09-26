# App de Gestão Financeira Pessoal — Requisitos

## Contexto

Aplicação PWA para gestão de finanças domésticas: registo de contas/faturas (recorrentes e pontuais), salário, e cálculo do que é necessário pagar num dado período (ativo vs. passivo). Substitui/automatiza um processo que atualmente é feito manualmente (levantamento de despesas, gestão de liquidez, uso de crédito para cobrir défices).

**Fase atual**: apenas análise de viabilidade e requisitos foi feita — este documento consolida essas decisões para servir de base à implementação.

## Instruções para o Claude Code

- Usar as **skills disponíveis** neste ambiente sempre que aplicável (ex: geração de PWA, componentes de UI, visualização de dados, etc.)
- Usar **pacotes npm** já estabelecidos e bem mantidos em vez de reinventar funcionalidade (ex: gráficos, datas, service worker/PWA tooling, ícones SVG)
- Aproveitar ao **máximo os recursos já existentes noutras apps deste projeto** (autenticação Google já implementada, ligação à base de dados existente na RPi, configuração de NTFY já em uso) em vez de recriar de raiz
- Design **moderno e minimalista**, com **ícones/SVG** (nunca emojis) para toda a iconografia
- Interface **dinâmica** (não páginas estáticas — transições, atualização de estado sem reload)
- Organização por **tabs** (não menu lateral nem páginas separadas por navegação tradicional)

## Arquitetura

- **Frontend**: PWA (HTML/JS), alojado no GitHub Pages
- **Backend**: API a correr na RPi, junto com as outras apps já existentes nesse servidor
- **Base de dados**: reutilizar a base de dados já existente na RPi — novas tabelas com prefixo `financas_` (não criar uma BD separada)
- **Notificações**: NTFY, já disponível na mesma RPi
- **Autenticação**: Google OAuth com token persistente, seguindo o mesmo padrão já usado nas outras apps deste ecossistema

## Modelo de dados

### Lançamentos (tabela unificada — não separar "contas" de "salário")

Cada lançamento tem:
- `tipo`: `despesa` ou `rendimento`
- `valor`
- `categoria` (lista aberta — ver secção Categorias)
- `data_vencimento`
- `data_pagamento` (pode ficar em branco = ainda pendente)
- `recorrente`: sim/não
- `mes_referencia` (para agrupar por ciclo mensal)

### Estados derivados (calculados, não guardados)
- **Pendente por vencer**: sem `data_pagamento`, `data_vencimento` no futuro
- **Vencido e não pago**: sem `data_pagamento`, `data_vencimento` já passada
- **Pago**: `data_pagamento` preenchida

### Categorias
- Lista aberta — o utilizador pode criar categorias novas livremente
- Categorias iniciais sugeridas: Habitação, Alimentação, Transportes, Lazer, Saúde, Outros (ver paleta de cores abaixo)

### Sem histórico de edições
- Não é necessário guardar auditoria de alterações a um lançamento já pago (edição simplesmente sobrescreve)
- Deve existir, no entanto, **histórico mensal agregado por conta/categoria** (para ver, por exemplo, a evolução da conta da luz ao longo dos meses)

## Fluxo de utilização

### Ciclo mensal
- Ao abrir a app num novo mês, apresentar os lançamentos do **mês anterior como default** (mesma lista, mesmos valores)
- Utilizador confirma, edita valores que mudaram (ex: água, luz), remove o que não se aplica, adiciona novos
- `data_pagamento` vem sempre em branco por default no novo mês (mesmo que `data_vencimento` venha pré-preenchida)
- O salário/rendimento entra pelo mesmo mecanismo, como um lançamento do tipo `rendimento`

### Cálculo ativo/passivo
- Calculado por janela temporal: 30 dias corridos ou mês civil (deve ser possível alternar/escolher)
- Fórmula base: rendimento esperado no período − soma de lançamentos `despesa` ainda sem `data_pagamento` no período
- Destacar visualmente os "vencidos e não pagos" como alerta

## Notificações (NTFY)

- Disparo **no dia do vencimento** de cada lançamento (não X dias antes)
- Aplica-se tanto a lançamentos recorrentes como pontuais

## Relatórios

- **Vista mensal**: total de despesas vs. rendimento, com detalhe por categoria
- **Vista anual**: evolução mês a mês
- **Comparação homóloga**: mesmo mês, anos diferentes (ex: luz set/2026 vs. luz set/2025)
- Gráficos devem usar a paleta de categorias definida abaixo (não apenas verde/vermelho)

## Design — Paleta de cores

| Função | Cor | HEX |
|---|---|---|
| Primária | Verde esmeralda escuro | `#146B55` |
| Primária clara | Verde suave | `#DDF3EA` |
| Primária hover | Verde profundo | `#0F5947` |
| Secundária | Azul petróleo | `#295B70` |
| Fundo geral | Cinza muito claro | `#F6F8F7` |
| Cards | Branco | `#FFFFFF` |
| Texto principal | Grafite | `#1D2925` |
| Texto secundário | Cinza | `#66736E` |
| Bordas | Cinza-esverdeado | `#DCE4E0` |
| Receita / positivo | Verde | `#239B6D` |
| Despesa / negativo | Vermelho suave | `#D9535F` |
| Aviso | Âmbar | `#E6A23C` |
| Informação | Azul | `#3B82B6` |

### Cores para categorias em gráficos (evitar depender só de verde/vermelho)

| Categoria | HEX |
|---|---|
| Habitação | `#476D7C` |
| Alimentação | `#D9A441` |
| Transportes | `#6C77A8` |
| Lazer | `#AA6F8E` |
| Saúde | `#4F9C8C` |
| Outros | `#8A918E` |

### Ícone
- Será fornecido na pasta do projeto (não gerar um novo)

## Fora de âmbito / decisões pendentes

- Relação entre esta app e o controlo manual já existente de saldos de cartões de crédito e prestações (ex: prestação de 12 meses acordada anteriormente) — a decidir se a app substitui ou coexiste com esse controlo, mais adiante
