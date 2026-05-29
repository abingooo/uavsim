#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-$ROOT_DIR/PX4-Autopilot}"

if [ ! -d "$PX4_DIR" ]; then
  printf 'PX4 source not found: %s\n' "$PX4_DIR" >&2
  printf 'Run scripts/setup_px4.sh first.\n' >&2
  exit 1
fi

cd "$PX4_DIR"
DONT_RUN=1 make px4_sitl_default none_iris
