#!/usr/bin/env bash
# push.sh — adiciona, faz commit e push de todo o projeto para o branch main.
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
echo "Concluído."
echo "Commit: $(git rev-parse --short HEAD)"
echo "Branch: main"
