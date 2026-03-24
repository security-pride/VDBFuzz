#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

if [[ ! -f .env && -f .env.example ]]; then
  cp .env.example .env
fi

"$ROOT_DIR/scripts/compose.sh" up -d
python3 scripts/wait_for_vdbs.py
