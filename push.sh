#!/usr/bin/env bash
# push.sh — adiciona, faz commit e push de todo o projeto para o branch main,
# e força de seguida uma reconstrução do GitHub Pages (o site fica servido
# a partir do branch main, tipo "legacy" — o GitHub já reconstrói sozinho a
# cada push, mas o pedido explícito à API garante que acontece mesmo assim
# e dá confirmação do resultado, incluindo quando não há nada para commitar).
#
# Uso:
#   ./push.sh                          # mensagem de commit gerada automaticamente
#   ./push.sh "mensagem de commit"     # mensagem de commit à escolha
#
# Corre a partir de qualquer diretoria (usa sempre a raiz deste repositório).

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

BRANCH_ATUAL="$(git branch --show-current)"
if [ "$BRANCH_ATUAL" != "main" ]; then
  echo "Erro: estás no branch '$BRANCH_ATUAL', não no 'main'. A abortar." >&2
  echo "Muda para main (git checkout main) antes de correr este script." >&2
  exit 1
fi

# ---------- GitHub Pages: pedir reconstrução e acompanhar o resultado ----------
forcar_deploy_pages(){
  if ! command -v gh >/dev/null 2>&1; then
    echo "Aviso: 'gh' não está instalado — a saltar o pedido de reconstrução do GitHub Pages." >&2
    return 0
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "Aviso: 'gh' não tem sessão autenticada — a saltar o pedido de reconstrução do GitHub Pages." >&2
    return 0
  fi

  local remote_url owner_repo
  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  owner_repo="$(echo "$remote_url" | sed -E 's#(git@github\.com:|https://github\.com/)##; s#\.git$##')"
  if [ -z "$owner_repo" ]; then
    echo "Aviso: não consegui identificar o repositório GitHub a partir do remote — a saltar o deploy." >&2
    return 0
  fi

  echo "A pedir reconstrução do GitHub Pages ($owner_repo)..."
  if ! gh api --method POST -H "Accept: application/vnd.github+json" "repos/$owner_repo/pages/builds" >/tmp/push-sh-pages-build.json 2>/tmp/push-sh-pages-build.err; then
    echo "Aviso: pedido de reconstrução falhou:" >&2
    cat /tmp/push-sh-pages-build.err >&2
    return 0
  fi

  local tentativas=0
  local estado=""
  while [ "$tentativas" -lt 8 ]; do
    sleep 5
    estado="$(gh api "repos/$owner_repo/pages/builds/latest" --jq '.status' 2>/dev/null || true)"
    if [ "$estado" = "built" ] || [ "$estado" = "errored" ]; then
      break
    fi
    tentativas=$((tentativas + 1))
  done

  case "$estado" in
    built)
      local url
      url="$(gh api "repos/$owner_repo/pages" --jq '.html_url' 2>/dev/null || true)"
      echo "GitHub Pages reconstruído com sucesso.${url:+ URL: $url}"
      ;;
    errored)
      echo "Aviso: a reconstrução do GitHub Pages terminou com erro — verifica em https://github.com/$owner_repo/settings/pages" >&2
      ;;
    *)
      echo "Reconstrução pedida, mas ainda em curso ao fim de ~40s — confirma mais tarde em https://github.com/$owner_repo/settings/pages"
      ;;
  esac
}

# Guarda de segurança: nunca deixar passar ficheiros que pareçam credenciais.
FICHEIROS_SENSIVEIS="$(git status --porcelain | awk '{print $2}' | grep -E '(^|/)\.env($|\.[^/]*$)|\.pem$|\.key$|credentials\.json$|serviceAccount.*\.json$' || true)"
if [ -n "$FICHEIROS_SENSIVEIS" ]; then
  echo "Erro: detetados ficheiros potencialmente sensíveis a caminho do commit:" >&2
  echo "$FICHEIROS_SENSIVEIS" >&2
  echo "Remove-os do staging ou adiciona-os a um .gitignore antes de continuar." >&2
  exit 1
fi

if [ -z "$(git status --porcelain)" ]; then
  echo "Nada para commitar — árvore de trabalho limpa."
  forcar_deploy_pages
  exit 0
fi

echo "Alterações a incluir no commit:"
git status --short

git add -A

MENSAGEM="${1:-chore: atualização automática $(date '+%Y-%m-%d %H:%M')}"
git commit -m "$MENSAGEM"

echo "A fazer push para origin/main..."
git push origin main

echo ""
forcar_deploy_pages

echo ""
echo "Concluído."
echo "Commit: $(git rev-parse --short HEAD)"
echo "Branch: main"
