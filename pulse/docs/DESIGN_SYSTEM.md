# Design System

## Direção

Pulse deve ter aparência:

- profissional;
- moderna;
- clean;
- futurista sem ser cyberpunk;
- completa;
- intencional;
- consistente;
- discreta;
- premium.

Não deve parecer:

- dashboard genérico;
- protótipo;
- template de IA;
- coleção aleatória de cartões;
- ferramenta interna de programador.

## Idioma

Idioma canónico: `pt-PT`.

Formatos:

- data: `28/09/2026`;
- data escrita: `28 de setembro`;
- hora: `17:42`;
- moeda: `1 245,50 €`;
- peso: `104,8 kg`.

## Paleta Light

| Token | Cor |
|---|---|
| Background | `#F7FAFC` |
| Surface | `#FFFFFF` |
| Primary | `#1E5B67` |
| Accent | `#22C7B8` |
| Text | `#16222A` |

## Paleta Dark

| Token | Cor |
|---|---|
| Background | `#0C1418` |
| Surface | `#142027` |
| Primary | `#56B8C4` |
| Accent | `#2DD4C3` |
| Text | `#EAF2F4` |

Estados adicionais:

- sucesso `#3CBF8A`;
- aviso `#D9A441`;
- erro `#D95C5C`;
- informação `#4A90D9`.

## Tipografia

Fonte preferida: Inter.

| Uso | Tamanho | Peso | Altura linha |
|---|---:|---:|---:|
| Métricas principais | 32 sp | 600 | 38 sp |
| Título página | 28 sp | 600 | 34 sp |
| Título secção | 22 sp | 600 | 28 sp |
| Título cartão | 18 sp | 500 | 24 sp |
| Corpo | 16 sp | 400 | 24 sp |
| Corpo secundário | 14 sp | 400 | 20 sp |
| Label/botão | 14 sp | 500 | 20 sp |
| Metadata | 12 sp | 400/500 | 16 sp |

Usar números tabulares onde façam sentido.

## Espaçamento

Base de 4 dp.

Tokens:

- 4;
- 8;
- 12;
- 16;
- 20;
- 24;
- 32;
- 40;
- 48;
- 64.

Margem horizontal normal: 20 dp.

## Radius

- XS: 6 dp;
- S: 8 dp;
- M: 12 dp;
- L: 16 dp;
- XL: 20 dp;
- Full: 50%.

`16 dp` é o raio principal.

## Cartões

- padding: 16–20 dp;
- raio: 16 dp;
- intervalo: 12–16 dp;
- elevação mínima;
- borda de 1 dp apenas quando necessária.

Evitar cartões dentro de cartões.

## Botões

- normal: 48 dp;
- destaque: 52 dp;
- compacto: 40 dp.

## Ícones

Nunca emojis.

Ícones:

- minimalistas;
- lineares;
- estilizados;
- coerentes;
- preferencialmente SVG;
- traço 1,75–2 dp.

Tamanhos:

- 20 dp inline;
- 24 dp padrão;
- 28 dp navegação;
- 32 dp destaque.

## Motion

- Instant: 100–120 ms;
- Fast: 160 ms;
- Normal: 220 ms;
- Emphasis: 300 ms;
- Transition: 350 ms.

Evitar animações decorativas contínuas.

## Loading

Pulse deve ter estados de carregamento tratados como parte do branding.

Asset oficial:

`assets/branding/pulse-loading.webp`

Características:

- transparente;
- discreto;
- reutilizável em Android e Web;
- adequado a splash/loading principal.

Tipos de loading:

1. arranque/splash;
2. loading principal;
3. loading inline;
4. sync;
5. IA.

Listas/cartões devem preferir skeletons quando isso melhora a perceção de desempenho.

## Privacidade visual

Dados sensíveis não são escondidos por defeito após autenticação.

O utilizador pode ativar:

- ocultar valores;
- modo de privacidade rápida;
- ocultar valores em widgets;
- ocultar conteúdo em notificações;
- proteção de previews/screenshot quando aplicável.

## Interações

Clique prolongado:

- atalhos no ícone Android;
- ações contextuais;
- reordenar favoritos/fixados.

Nunca deve ser a única forma de aceder a uma funcionalidade essencial.

## Ecrãs de acesso (início de sessão e mudança de palavra-passe)

- Ecrãs limpos, centrados, com o asset de marca e um só objetivo cada; nada de cartões dentro de cartões.
- Campos de 48 dp, raio 12 dp, rótulo sempre visível (não só placeholder), erro por baixo do campo e em pt-PT
  («E-mail ou palavra-passe incorretos», «A palavra-passe tem de ter pelo menos 10 caracteres»).
- Palavras-passe com mostrar/ocultar e compatíveis com gestores de passwords (`autocomplete` correto na Web,
  autofill no Android).
- O botão principal (52 dp) mostra loading no próprio botão e desativa-se durante o pedido; erros 429 explicam que há
  demasiadas tentativas, sem contagens exatas nem dicas sobre que contas existem.
- Estados: loading, erro, sucesso e degradado (servidor indisponível); Light e Dark com paridade.
