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
export PX4_SIM_MODEL="${PX4_SIM_MODEL:-iris}"

BIN="$PX4_DIR/build/px4_sitl_default/bin/px4"
ROOTFS="$PX4_DIR/ROMFS/px4fmu_common"
BUILD_DIR="$PX4_DIR/build/px4_sitl_default"
TEST_DATA="$PX4_DIR/test_data"

if [ ! -x "$BIN" ]; then
  printf 'PX4 SITL binary not found: %s\n' "$BIN" >&2
  printf 'Run scripts/build_px4_sitl.sh first.\n' >&2
  exit 1
fi

mkdir -p "$BUILD_DIR/instance_0"
cd "$BUILD_DIR/instance_0"
if [ -t 0 ]; then
  exec "$BIN" -i 0 "$ROOTFS" -s etc/init.d-posix/rcS -t "$TEST_DATA"
else
  "$BIN" -i 0 "$ROOTFS" -s etc/init.d-posix/rcS -t "$TEST_DATA" < <(tail -f /dev/null)
fi
