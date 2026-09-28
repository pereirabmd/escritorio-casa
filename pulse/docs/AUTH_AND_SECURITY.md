# Autenticação e segurança

## Android

Fluxo de conta:

```text
Continuar com Google
 -> identidade Google validada
 -> backend cria/encontra utilizador Pulse
 -> backend emite sessão Pulse
```

Após configuração inicial, o Android exige:

- PIN;
- biometria opcional/permitida como desbloqueio rápido.

Biometria/PIN são aplicados no arranque/desbloqueio da app, não por módulo.

## Web

- login Google;
- sem PIN;
- sem biometria;
- sessão persistente segura.

## Google OAuth

Login Pulse e ligação de contas Google são conceitos separados.

O utilizador pode:
- entrar no Pulse com uma conta Google;
- ligar outras contas para Gmail/Calendar/Tasks.

Refresh tokens:
- ficam no servidor;
- encriptados em repouso;
- nunca são devolvidos ao Android/Web;
- scopes mínimos;
- revogáveis.

Nunca guardar passwords Google.

## Dados sensíveis

Depois de autenticado, os dados não ficam ocultos por defeito.

Privacidade opcional:
- ocultar saldos;
- ocultar peso;
- ocultar contas;
- modo rápido de privacidade;
- ocultar notificações no lock screen;
- ocultar valores em widgets;
- proteger preview da app quando configurado.

## IA

Permissões:
- read;
- safe_action;
- sensitive_action.

Ações sensíveis/destrutivas exigem confirmação.

IA nunca escreve diretamente em BDs.

## Segredos

Nunca hardcode:
- Google secrets;
- FCM keys;
- chaves de IA;
- tokens;
- passwords;
- credenciais SMTP/serviços.

Usar secrets/env no servidor.

## Atualizações APK

APK fora da Play Store:
- validar versão;
- descarregar via fonte oficial;
- mesma chave de assinatura;
- não instalar silenciosamente;
- respeitar fluxo de instalação Android.

## Sessões

Prever:
- revogação;
- expiração;
- gestão de dispositivos;
- logout remoto;
- invalidação de tokens.
