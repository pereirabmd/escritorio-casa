# Compras — catálogo de série

Fonte: `pulse/server/pulse/compras_catalogo.py` (338 produtos em 13 corredores, por ordem de corredor). Ícones: `pulse/web/src/assets/shop-icons.json` (73). Decisões em `DECISIONS.md` (ADR-047).

| Corredor | Produtos |
|---|---|
| Frutas e legumes | 41 |
| Padaria e pastelaria | 11 |
| Mercearia | 89 |
| Laticínios e ovos | 24 |
| Carne | 19 |
| Peixe | 14 |
| Congelados | 14 |
| Bebidas | 16 |
| Higiene pessoal | 36 |
| Limpeza | 38 |
| Casa e bazar | 11 |
| Bebé e crianças | 9 |
| Gato | 16 |

Regras para o manter:
- **Acrescentar** produtos é seguro: entram no arranque seguinte do servidor.
- **Renomear** um produto de série: indicar o slug antigo (`Nome novo|icone|slug-antigo`), senão nasce um produto novo e o antigo fica órfão (com os favoritos e itens de quem o usava).
- **Nunca apagar** um produto do ficheiro para o "tirar": o arranque não apaga, e quem o tem em listas continua a vê-lo. Para esconder, cada conta usa «Esconder do catálogo».
- Um teste (`test_compras.py`) valida: sem duplicados (slug e nome), ícones existentes, categorias válidas e que o servidor e a Web têm os mesmos ícones.
- Ficaram de fora de propósito: medicamentos, alimentação de outros animais, produtos de jardim/bricolage. Quem precisar cria o produto (categoria «Outros» por omissão).
- **Esconder categorias**: cada conta esconde as que não usa (Catálogo → Gerir); não afeta o catálogo nem as outras contas.

