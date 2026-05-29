#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"$ROOT_DIR/scripts/stop_px4.sh"
"$ROOT_DIR/scripts/stop_blocks.sh"
pkill -f 'scripts/qgc_udp_sink.py' || true

printf 'Stopped PX4 and AirSim Blocks if they were running.\n'
