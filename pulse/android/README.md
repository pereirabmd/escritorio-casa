# Pulse — app Android

Kotlin + Jetpack Compose + Material 3. Decisões em `../docs/DECISIONS.md` (ADR-026, 034, 035, 050, 051); estado face à Web em `../docs/PARITY_ANDROID.md`.

- Compilar/testar: `JAVA_HOME=<jdk17> ANDROID_HOME=~/Android/Sdk ~/.local/opt/gradle-8.7/bin/gradle :app:testDebugUnitTest :app:assembleRelease` (definições de memória em `gradle.properties`, ADR-035).
- Assinatura: `~/.local/keystores/pulse.jks` + `pulse-keystore.properties` (fora do repositório, ADR-034). Sem elas o `assembleRelease` sai sem assinatura de produção.
- Publicar: subir `versionCode`/`versionName` em `app/build.gradle` e correr `../scripts/deploy/publicar_apk.sh "notas"`. O APK fica em `https://bmdpereira.duckdns.org/pulse/apk/pulse.apk`.
- Notificações: o `app/google-services.json` (Firebase, projeto `bmdpereira-5a8f4`) fica fora do Git; copiar de `pulse/google-services.json` antes de compilar (ADR-057).
- Servidor: `BuildConfig.SERVER` em `app/build.gradle`.
- Ecrãs em `app/src/main/java/pt/pereirabmd/pulse/ui`; dados/API em `data`; formatos pt-PT em `util` (espelham `web/src/lib`).
- Testes unitários (JVM) em `app/src/test`: formatos, regras de palavra-passe, leitura do JSON do servidor, PIN e atualização. A interface só foi verificada por compilação: testar no telemóvel.

- Módulos nativos em `ui/*Ecra.kt`, um por módulo (e `Base.kt` com o que é comum: cargas, ações com «Desfazer», folhas, seletores). A tabela de paridade com a Web está em `../docs/PARITY_ANDROID.md`.
