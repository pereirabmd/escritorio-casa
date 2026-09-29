#!/usr/bin/env bash
# Compila o APK do Pulse (release, assinado com a chave do ADR-034) e publica-o no Pi em /opt/pulse/apk/, ao lado de um
# version.json que a app lê para se atualizar (ADR-026). Não toca em releases do servidor nem em dados.
#   /opt/pulse/apk/pulse-<versao>.apk   uma por versão (guarda as 3 últimas)
#   /opt/pulse/apk/pulse.apk            a mais recente, com endereço fixo (é o link da página de resumo)
#   /opt/pulse/apk/version.json         {versionCode, versionName, url, sha256, notas}
# Uso: pulse/scripts/deploy/publicar_apk.sh ["notas da versão"]
# O versionCode/versionName vêm de android/app/build.gradle: subir o versionCode antes de cada publicação.
set -euo pipefail
PI="${PULSE_PI:-casamento-pi}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NOTAS="${1:-}"
GRADLE="${GRADLE:-$HOME/.local/opt/gradle-8.7/bin/gradle}"
export JAVA_HOME="${JAVA_HOME:-$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")}"
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Android/Sdk}"

CODE="$(sed -n "s/^ *versionCode \([0-9]*\).*/\1/p" "$RAIZ/android/app/build.gradle")"
NAME="$(sed -n "s/^ *versionName '\(.*\)'.*/\1/p" "$RAIZ/android/app/build.gradle")"
[ -n "$CODE" ] && [ -n "$NAME" ] || { echo "versionCode/versionName não encontrados em build.gradle" >&2; exit 1; }
[ -f "$HOME/.local/keystores/pulse-keystore.properties" ] || { echo "Falta a chave de assinatura (~/.local/keystores/pulse-keystore.properties): sem ela o APK sairia sem assinatura de produção." >&2; exit 1; }

# a versão não pode andar para trás: o Android recusa instalar por cima uma versionCode igual ou menor
ATUAL="$(ssh "$PI" 'cat /opt/pulse/apk/version.json 2>/dev/null || true' | sed -n 's/.*"versionCode": *\([0-9]*\).*/\1/p')"
if [ -n "$ATUAL" ] && [ "$CODE" -le "$ATUAL" ]; then echo "versionCode $CODE não é maior do que o publicado ($ATUAL): sobe-o em android/app/build.gradle." >&2; exit 1; fi

( cd "$RAIZ/android" && "$GRADLE" -q :app:testDebugUnitTest :app:assembleRelease )
APK="$RAIZ/android/app/build/outputs/apk/release/app-release.apk"
"$ANDROID_HOME/build-tools/34.0.0/apksigner" verify "$APK"
SHA="$(sha256sum "$APK" | cut -d' ' -f1)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp "$APK" "$TMP/pulse-$NAME.apk"; cp "$APK" "$TMP/pulse.apk"
python3 - "$CODE" "$NAME" "$SHA" "$NOTAS" > "$TMP/version.json" <<'PY'
import json, sys
c, n, s, notas = sys.argv[1:5]
print(json.dumps({"versionCode": int(c), "versionName": n, "url": f"pulse-{n}.apk", "sha256": s, "notas": notas}, ensure_ascii=False, indent=2))
PY

ssh "$PI" "mkdir -p /opt/pulse/apk"
# o APK primeiro e o version.json por último: a app nunca vê uma versão anunciada cujo ficheiro ainda não existe
rsync -a "$TMP/pulse-$NAME.apk" "$TMP/pulse.apk" "$PI:/opt/pulse/apk/"
rsync -a "$TMP/version.json" "$PI:/opt/pulse/apk/"
ssh "$PI" "ls -1t /opt/pulse/apk/pulse-*.apk | tail -n +4 | xargs -r rm -f"
echo "Publicado: pulse-$NAME.apk (versionCode $CODE, sha256 ${SHA:0:12}…)"
# um pedido que caia no index da SPA também dá 200: por isso confere-se o conteúdo, não só o estado
URL="https://bmdpereira.duckdns.org/pulse/apk"
if curl -fsS "$URL/version.json" | python3 -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('versionCode') == $CODE else 1)" 2>/dev/null \
   && curl -fsSI "$URL/pulse.apk" | grep -qi "content-type: application/vnd.android.package-archive"; then
  echo "OK $URL/pulse.apk"
else
  echo "AVISO: $URL ainda não serve o APK (falta o bloco nginx «location ^~ /pulse/apk/» de pulse/infra/nginx/pulse-web.conf)" >&2
fi
