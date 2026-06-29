#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEER_DIR="$ROOT_DIR/peer-repo"

required_files=(
  "newslettr-status.md"
  "atacama-status.md"
  "trakaido-status.md"
  "greenland-status.md"
  "trakaido-prodconfig-status.md"
)

required_sections=(
  "## Repository Overview"
  "## Current State"
)

status=0

for file in "${required_files[@]}"; do
  path="$PEER_DIR/$file"
  if [[ ! -f "$path" ]]; then
    echo "[ERROR] Missing required file: $path"
    status=1
    continue
  fi

  if ! head -n 1 "$path" | rg -q '^# .+ - Current Status$'; then
    echo "[ERROR] Invalid title format in $file (expected '# <Repo> - Current Status')"
    status=1
  fi

  for section in "${required_sections[@]}"; do
    if ! rg -q "^${section}$" "$path"; then
      echo "[ERROR] Missing section '${section}' in $file"
      status=1
    fi
  done

done

if [[ $status -eq 0 ]]; then
  echo "[OK] .agents documentation structure is valid"
fi

exit "$status"
