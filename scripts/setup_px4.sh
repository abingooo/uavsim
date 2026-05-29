#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="${PX4_DIR:-$ROOT_DIR/PX4-Autopilot}"
PX4_REF="${PX4_REF:-v1.11.3}"

if [ ! -d "$PX4_DIR/.git" ]; then
  git clone https://github.com/PX4/PX4-Autopilot.git "$PX4_DIR"
fi

git -C "$PX4_DIR" fetch --tags
git -C "$PX4_DIR" checkout "$PX4_REF"
git -C "$PX4_DIR" submodule sync --recursive
git -C "$PX4_DIR" submodule update --init --recursive

printf '\nPX4 source is ready at %s, ref %s.\n' "$PX4_DIR" "$PX4_REF"
printf 'If dependencies are not installed yet, run:\n'
printf '  bash "%s/Tools/setup/ubuntu.sh" --no-nuttx --no-sim-tools\n' "$PX4_DIR"
printf '\nThen build SITL:\n'
printf '  PX4_DIR="%s" scripts/build_px4_sitl.sh\n' "$PX4_DIR"
