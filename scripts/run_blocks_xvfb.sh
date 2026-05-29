#!/usr/bin/env bash
set -euo pipefail

if ! command -v xvfb-run >/dev/null 2>&1; then
  printf 'xvfb-run not found. Install xvfb or run scripts/run_blocks.sh from a graphical session.\n' >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec xvfb-run -a "$SCRIPT_DIR/run_blocks.sh"
