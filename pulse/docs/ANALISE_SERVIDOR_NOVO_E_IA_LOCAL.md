# Análise: mudar para um servidor mais potente e migrar o assistente de IA para um modelo local

Estado: **análise, nenhuma decisão tomada** (01/10/2026). As partes marcadas «medido» foram lidas no Pi nesse dia; as marcadas «estimativa» **não foram medidas**.

## 1. Ponto de partida (medido, 01/10/2026)
- Pi 3B: 4 núcleos a 1,2 GHz, 1 GB de RAM, cartão SD de 29 GB (26 % usado), já com Debian 13.
- Carga média 0,4; 455 MB de RAM em uso (inclui o ambiente gráfico, que ninguém usa); 45 °C.
- Dados pequenos: `dados` 4,7 MB, Pulse 0,8 MB.
- Serviços: `pulse-api`, `dados-api`, `dados-admin`, `cp-scheduler`, `tarefas-api`, nginx, ntfy, `casamento-rsvp`, mais o cron dos Bilhetes (`pedidos.py` e `live_delay.py` de minuto a minuto).
- O agente de IA (`services/ia.py`, ADR-077) usa o Claude Haiku 4.5 pela API da Anthropic, com ferramentas (as ações do catálogo), até 6 voltas por comando e 12 pedidos por minuto. O modelo nunca escreve: as escritas são propostas que o utilizador confirma. A voz (reconhecimento e leitura) é do Android, não do modelo.

## 2. Servidor candidato
Ryzen 7 7735HS (8C/16T, até 4,75 GHz), 24 GB LPDDR5-5500, NVMe de 512 GB com 2 slots M.2, Radeon 680M, Wi-Fi 6, 2,5 GbE, Debian 13.

### Ganhos (estimativa)
- **Compra a T: quase nenhum.** O tempo é quase todo rede até à CP (60 a 300 ms por pedido) e TLS; a CPU conta pouco (no máximo dezenas de ms).
- **Fiabilidade: o maior ganho.** NVMe em vez do cartão SD (o ponto frágil de um Pi que escreve logs e bases 24 h); o 2.º slot M.2 serve para espelho (RAID1).
- **Operação:** primeiro arranque de cada release do Pulse (hoje cerca de 1 min) e `pip install` mais rápidos. Os testes e a compilação da Web já correm no PC do utilizador.
- **Folga:** deixam de existir limites apertados (`MemoryMax=200M` do Pulse); abre caminho a IA local.
- 2,5 GbE e Wi-Fi 6 não ajudam (o limite é a ligação à internet).

### Custos e riscos
- Energia: 8 a 15 W parado contra 3 a 4 W do Pi, cerca de 20 a 30 € por ano a 0,20 €/kWh (estimativa).
- Migração de cerca de meio dia: `/opt/pulse`, `~/dados`, `~/bilhetes_cp` com as chaves (`BILHETES_FERNET_KEY`, FCM, `PULSE_SERVICE_KEY`) e `tokens/`; nginx e certificado, DuckDNS e encaminhamento de portas do router, fail2ban, serviços systemd, cron, ntfy.
- Coisas que partem: o IP `192.168.68.103` no `index.html` e nas verificações «rede de casa» (`na_lan`, `_ip_publico_de_casa`); o alias SSH `casamento-pi` nos scripts de deploy.
- **Compra duplicada:** só uma máquina pode ter o `cp-scheduler` ativo. Fazer o corte longe de qualquer T e manter o Pi como reserva uns dias, com o scheduler desligado nele.
- Mais ruído e manutenção do que um Pi.

### Alternativa barata
Manter o Pi, sem ambiente gráfico (liberta cerca de 200 MB) e com a raiz num SSD USB: resolve o risco do cartão SD por poucos euros.

## 3. Assistente de IA com modelo local (Llama e outros)
### Viabilidade (estimativa)
- 7 a 8 mil milhões de parâmetros (4,7 GB): cerca de 8 a 14 tokens/s. 14 mil milhões (9 GB): 5 a 7 tokens/s. 70 mil milhões: não cabem nos 24 GB.
- O assistente envia o esquema de dezenas de ações a cada volta (milhares de tokens): na CPU a 1.ª volta demora dezenas de segundos; com cache do prefixo fixo (llama.cpp) as seguintes ficam rápidas. Um comando completo: cerca de 10 a 40 s, contra poucos segundos hoje.
- A Radeon 680M ajuda pouco (ROCm não a suporta oficialmente; só o Vulkan do llama.cpp).
- **Qualidade:** escolher a ação certa entre dezenas, com JSON e em português, é a parte difícil; um Llama 3.1 de 8B falha bastante. Qwen3 de 8B a 14B costuma usar melhor as ferramentas: testar os dois.
- Segurança do desenho: como o modelo nunca escreve, um modelo pior produz mais propostas erradas, não estragos.

### Custos e riscos
- Os pesos são gratuitos, mas a licença do Llama tem condições. O Haiku custa pouco para uso doméstico (a fatura real não foi consultada).
- Privacidade melhora: os dados deixam de sair de casa.
- Uma inferência a usar os 8 núcleos pode atrasar os scripts de compra: limitar com `CPUQuota`/`nice` e não correr perto de um T.
- O assistente deixa de funcionar se o servidor local estiver ocupado ou em baixo.
- Código: o `ia.py` fala o formato da Anthropic; llama.cpp e Ollama falam o formato OpenAI (`/v1/chat/completions` com ferramentas). É preciso um adaptador (meio dia a um dia) mais avaliação; o `transporte` já existe para testes.

### Plano proposto (por esta ordem)
1. Migrar para o servidor novo, se o utilizador avançar.
2. Montar 30 a 50 comandos reais do utilizador e correr no Claude e em 2 a 3 modelos locais (Llama 3.1 8B, Qwen3 8B e 14B), medindo a escolha da ação, os parâmetros e o tempo.
3. Só migrar se um modelo local acertar quase tudo; senão manter o Claude como principal e o local só como reserva sem internet.

## 4. Perguntas em aberto (para o utilizador)
- Avançar só com a avaliação dos modelos num PC emprestado, antes de comprar ou migrar o servidor?
- Quanto se gasta hoje na API da Anthropic (para comparar com a energia do servidor novo)?
- Avançar com um plano de migração detalhado (ficheiros, serviços e ordem do corte)?
