#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AIRSIM_DIR="${AIRSIM_DIR:-/home/uav/DataDisk/PAB/AirSim}"
UE4_EDITOR="${UE4_EDITOR:-/home/uav/DataDisk/PAB/UnrealEngine/Engine/Binaries/Linux/UE4Editor}"
BLOCKS_PROJECT="${BLOCKS_PROJECT:-$AIRSIM_DIR/Unreal/Environments/Blocks 4.27/Blocks.uproject}"
PX4_DIR="${PX4_DIR:-$ROOT_DIR/PX4-Autopilot}"

ok() {
  printf '[OK]   %s\n' "$1"
}

warn() {
  printf '[WARN] %s\n' "$1"
}

fail() {
  printf '[MISS] %s\n' "$1"
}

printf 'uavsim root: %s\n' "$ROOT_DIR"

for cmd in git cmake make python3 clang g++; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$cmd: $(command -v "$cmd")"
  else
    fail "$cmd not found"
  fi
done

if [ -d "$AIRSIM_DIR" ]; then
  ok "AirSim directory: $AIRSIM_DIR"
else
  fail "AirSim directory not found: $AIRSIM_DIR"
fi

if [ -x "$UE4_EDITOR" ]; then
  ok "UE4Editor: $UE4_EDITOR"
else
  fail "UE4Editor not executable: $UE4_EDITOR"
fi

if [ -f "$BLOCKS_PROJECT" ]; then
  ok "Blocks project: $BLOCKS_PROJECT"
else
  fail "Blocks project not found: $BLOCKS_PROJECT"
fi

if [ -d "$PX4_DIR" ]; then
  ok "PX4 source: $PX4_DIR"
  if [ -x "$PX4_DIR/build/px4_sitl_default/bin/px4" ]; then
    ok "PX4 SITL binary built"
  else
    warn "PX4 SITL binary not built yet"
  fi
else
  warn "PX4 source not found yet: $PX4_DIR"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  if nvidia-smi --query-gpu=name,driver_version --format=csv,noheader >/dev/null 2>&1; then
    ok "NVIDIA driver is responding"
  else
    warn "nvidia-smi exists but NVIDIA driver is not responding"
  fi
else
  warn "nvidia-smi not found"
fi

printf '\nNext:\n'
printf '  1. Install/build PX4: scripts/setup_px4.sh\n'
printf '  2. Install AirSim settings: scripts/install_settings.sh\n'
printf '  3. Start the full simulator: scripts/run_sim.sh\n'
printf '  4. Check simulator status: scripts/status_sim.sh\n'
printf '  5. Stop the full simulator: scripts/stop_sim.sh\n'
