# Definições e Administração

## Objetivo

A configuração técnica deve ser persistente e transparente para o utilizador.

## Secções

### Conta Pulse
- perfil;
- **mudar palavra-passe** (ecrã próprio; ver «Ecrã de mudança de palavra-passe» abaixo);
- sessão;
- logout;
- dispositivos: lista de sessões (Web/Android, dispositivo, último uso) com «Terminar sessão» em cada uma.

#### Ecrã de mudança de palavra-passe
- **Primeiro acesso:** as contas são criadas pelo administrador com uma palavra-passe provisória (ADR-037). Enquanto a
  conta tiver `mudarPassword = true` (devolvido por `POST /auth/login` e `GET /auth/me`), a app mostra **só** este ecrã, sem
  navegação nem acesso aos módulos, até a palavra-passe ser mudada (a API recusa o resto com 403 `mudar_password`).
- **Depois:** o mesmo ecrã em Definições → Conta, sem o bloqueio.
- Campos: palavra-passe atual, nova e confirmação (a confirmação valida-se só na app); cada campo com mostrar/ocultar.
- A nova mostra as regras enquanto se escreve: mínimo de 10 caracteres, não previsível (nada como o e-mail ou `1234567890`),
  não repetitiva e diferente da atual. A validação final é do servidor (`POST /auth/password`; códigos `password_fraca`,
  `password_atual_errada`, `password_igual`), e as mensagens vão em pt-PT.
- Depois de mudar: as **outras** sessões terminam (a atual continua) e a app diz-o («Terminámos as outras sessões»).
- Estados loading, erro e sucesso; Light/Dark com paridade; sem emojis; acessibilidade (labels, foco, gestores de passwords).
- «Esqueci-me da palavra-passe» não é automático (sem e-mail): o ecrã de início de sessão diz que é o administrador que a
  repõe e não pede nenhum e-mail.
- Administração de contas (criar, repor, desativar): por agora só na linha de comandos do servidor (`pulse.cli`); um ecrã de
  administração fica para depois, em «Administração avançada».

### Contas Google
- adicionar;
- remover;
- nome;
- email;
- estado;
- última sincronização;
- serviços ativos.

### Serviços Google
Por conta:
- Gmail;
- Calendar;
- Tasks.

### Módulos
- ativar/desativar;
- organização;
- favoritos;
- fixados.

### Sincronização
- estado;
- pendentes;
- erros;
- última sync;
- sincronização manual.

### Notificações
- Calendar;
- Tarefas;
- Email importante;
- Bilhetes CP;
- RTO;
- Finanças;
- sistema;
- IA quando implementada.

### Privacidade
- ocultar dados sensíveis;
- privacidade rápida;
- widgets;
- notificações lock screen;
- proteção de preview.

### Aparência
- claro;
- escuro;
- sistema.

### Atualizações
- versão atual;
- procurar atualizações;
- download por Wi-Fi;
- changelog.

### Sistema
- estado backend;
- integrações;
- versão;
- diagnóstico amigável.

### Administração avançada
Apenas quando necessário:
- endpoints;
- estado serviços;
- logs resumidos;
- ferramentas de recuperação.

## Persistência

As preferências devem ficar associadas à conta Pulse no backend para serem recuperadas entre dispositivos e Web/Android quando aplicável.
