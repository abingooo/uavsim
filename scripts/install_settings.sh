#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$ROOT_DIR/configs/settings_px4_sitl.json}"
DST_DIR="${AIRSIM_SETTINGS_DIR:-$HOME/Documents/AirSim}"
DST="$DST_DIR/settings.json"

if [ ! -f "$SRC" ]; then
  printf 'Settings template not found: %s\n' "$SRC" >&2
  exit 1
fi

mkdir -p "$DST_DIR"
if [ -f "$DST" ]; then
  cp "$DST" "$DST.bak.$(date +%Y%m%d_%H%M%S)"
fi

cp "$SRC" "$DST"
printf 'Installed AirSim settings: %s\n' "$DST"
