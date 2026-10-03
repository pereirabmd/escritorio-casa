# IA do Pulse

## Objetivo

A IA do Pulse deve:

1. compreender contexto consolidado;
2. pesquisar;
3. resumir;
4. recomendar ações contextuais;
5. executar ações autorizadas.

## Infraestrutura nesta fase

Mesmo que o agente final seja implementado no fim, a arquitetura deve incluir desde início:

- Action/Tool registry;
- permissões;
- validação;
- confirmações;
- idempotência;
- audit log;
- contratos de ação;
- APIs oficiais dos módulos.

## Níveis

### read
Consulta apenas.

Exemplos:
- eventos de amanhã;
- tarefas pendentes;
- próximo comboio;
- histórico de peso.

### safe_action
Ações reversíveis ou de baixo risco.

Exemplos:
- concluir tarefa;
- adiar tarefa;
- adicionar item à lista de compras;
- marcar dia RTO quando permitido.

### sensitive_action
Ações destrutivas, financeiras, externas ou com impacto relevante.

Exemplos:
- apagar;
- enviar email;
- operações sensíveis;
- alterações que não sejam facilmente reversíveis.

Devem exigir confirmação.

## Regra absoluta

A IA não executa SQL direto.

```text
IA
 -> Action Layer
 -> autorização/validação
 -> API/Core oficial
 -> dado
```

## Auditoria

Registar:
- ação;
- módulo;
- origem IA;
- utilizador;
- timestamp;
- resultado;
- confirmação quando aplicável.

## Detalhes posteriores

Prompts, modelo, contexto ideal, UX conversacional e regras específicas por ação podem ser afinados na fase final.

## Ferramentas de leitura do assistente (ADR-077, ampliadas no ADR-094)
Além das ações do catálogo (propostas que o utilizador confirma), o assistente tem leituras que correm logo, em nome da conta e só para os módulos a que tem acesso:

| Ferramenta | O que devolve | Notas |
|---|---|---|
| `consultar_hoje` | tarefas, bilhete, RTO, peso, contas, compras, eventos, emails | `modulos` limita |
| `compras_procurar` | produtos do catálogo e se estão na lista | usar sempre antes de adicionar |
| `bilhetes_favoritos` | comboios favoritos | só com o módulo Bilhetes |
| `consultar_tempo` | agora, hoje e os próximos 5 dias (Open-Meteo, pelo servidor) | usa a posição que o telemóvel manda em `posicao` (`lat`/`lon`, só para este pedido, nunca guardada); sem ela, Aveiro, e o assistente diz-o |
| `bilhetes_na_cp` | bilhetes futuros na CP (venda, data, hora, percurso, comboio, carruagem, lugar, valor, se se pode cancelar) | a `venda` é interna e nunca se diz ao utilizador; a referência da CP não vai ao modelo |
| `simular_devolucao` | a CP deixa devolver? quanto se recebe? | só leitura; precisa da `venda` de `bilhetes_na_cp` |
| `bilhetes_historico` | pedidos à CP dos últimos dias (contagem por resposta e os 20 mais recentes) | só o administrador (o `dados-api` recusa os outros); detalhe cortado a 80 caracteres |

`POST /ai/command` aceita `posicao: {lat, lon}` opcional. Trocas (`bilhetes.troca_armar`): o assistente consulta `bilhetes_na_cp` e `simular_devolucao`, propõe a troca e, **no mesmo comboio**, avisa do risco (devolve-se o atual e compra-se logo a seguir: outra pessoa pode apanhar o lugar) e de que só compensa se o bilhete atual foi comprado sem desconto. «Registar o RTO de hoje» usa `rto.marcar_dia` (T = escritório, C = casa).
