# escritorio-casa — como trabalhar com o utilizador

Estas regras valem para todas as mini-apps e para o Pulse (o `pulse/CLAUDE.md` acrescenta as do Pulse).

## Perguntar antes de implementar
- Antes de implementar algo novo ou que mude comportamento, **questionar cada decisão em aberto até não haver dúvidas**: âmbito, onde fica, quem vê, que dados, o que acontece nos casos limite, paridade Web/APK.
- Perguntar **uma decisão de cada vez**, com opções concretas e uma recomendação (a primeira, marcada «Recomendado»). Não fazer perguntas cujo valor por omissão é óbvio: escolher e dizê-lo.
- **Não voltar a perguntar o que já foi decidido** (nas memórias, nos ADR ou na conversa). Se o âmbito já foi dito com clareza, avançar.
- Se uma resposta for ambígua ou truncada, confirmar o que significa em vez de adivinhar.
- Se uma decisão conflitar com uma regra anterior do utilizador (ex.: no APK tudo é nativo, nunca abrir a Web), dizê-lo e perguntar antes de avançar.
- Correções de erros claros (um bug com causa identificada) não precisam de discussão: corrigir, testar e explicar.

## Publicar
- Commits sempre por `./push.sh "mensagem"` (ver o `git status` antes: o `push.sh` faz `git add -A`).
- Deploys no Pi (`deploy_pi.sh`, `dados-api`, scripts do `bilhetes_cp`, `publicar_apk.sh`) só com autorização expressa do utilizador, pela ordem: servidor, scripts do Pi, APK. Fazer cópia de segurança antes de substituir ficheiros no Pi.
- Dizer sempre o que está no GitHub, o que está no Pi e o que está instalado no telemóvel: são três coisas diferentes.
