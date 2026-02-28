#!/usr/bin/env bash
set -euo pipefail

CONTENT_DIR="${1:-content}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Error: run this script inside a git repository." >&2
  exit 1
fi

if [[ ! -d "$CONTENT_DIR" ]]; then
  echo "Error: directory '$CONTENT_DIR/' does not exist." >&2
  exit 1
fi

if [[ -z "$(git status --porcelain -- "$CONTENT_DIR")" ]]; then
  echo "No changes found in '$CONTENT_DIR/*'."
  exit 0
fi

echo "Changes found in '$CONTENT_DIR/*':"
git status --short -- "$CONTENT_DIR"

echo
read -r -p "Commit these changes now? [y/N] " answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  echo "Skipped commit."
  exit 0
fi

git add -- "$CONTENT_DIR"

if git diff --cached --quiet -- "$CONTENT_DIR"; then
  echo "Nothing staged for commit in '$CONTENT_DIR/*'."
  exit 0
fi

read -r -p "Commit message [Update content]: " commit_message
commit_message="${commit_message:-Update content}"

git commit -m "$commit_message"
