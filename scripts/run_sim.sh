#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs}"
AIRSIM_LAUNCHER="${AIRSIM_LAUNCHER:-$ROOT_DIR/scripts/run_blocks.sh}"
AIRSIM_NAME="${AIRSIM_NAME:-AirSim}"
STAMP="$(date +%Y%m%d_%H%M%S)"
PX4_LOG="$LOG_DIR/px4_$STAMP.log"
AIRSIM_LOG="$LOG_DIR/airsim_$STAMP.log"
QGC_SINK_LOG="$LOG_DIR/qgc_udp_sink_$STAMP.log"

mkdir -p "$LOG_DIR"

if pgrep -x px4 >/dev/null 2>&1; then
  printf 'PX4 already appears to be running. Stop it first with scripts/stop_sim.sh\n' >&2
  exit 1
fi

if pgrep -x UE4Editor >/dev/null 2>&1; then
  printf 'UE4Editor already appears to be running. Stop it first with scripts/stop_sim.sh\n' >&2
  exit 1
fi

if [ "${START_QGC_UDP_SINK:-0}" = "1" ]; then
  printf 'Starting local QGC UDP sink on 127.0.0.1:14550...\n'
  nohup python3 "$ROOT_DIR/scripts/qgc_udp_sink.py" >"$QGC_SINK_LOG" 2>&1 &
  QGC_SINK_PID=$!
  printf 'QGC UDP sink PID: %s\n' "$QGC_SINK_PID"
  printf 'QGC UDP sink log: %s\n' "$QGC_SINK_LOG"
fi

printf 'Starting PX4 SITL...\n'
nohup "$ROOT_DIR/scripts/run_px4_sitl.sh" >"$PX4_LOG" 2>&1 &
PX4_PID=$!

printf 'PX4 wrapper PID: %s\n' "$PX4_PID"
printf 'PX4 log: %s\n' "$PX4_LOG"

printf 'Waiting briefly before starting %s...\n' "$AIRSIM_NAME"
sleep "${PX4_START_DELAY:-5}"

printf 'Starting AirSim with launcher %s on DISPLAY=%s...\n' "$AIRSIM_LAUNCHER" "${DISPLAY:-:0}"
nohup "$AIRSIM_LAUNCHER" >"$AIRSIM_LOG" 2>&1 &
AIRSIM_PID=$!

printf 'AirSim wrapper PID: %s\n' "$AIRSIM_PID"
printf 'AirSim log: %s\n' "$AIRSIM_LOG"
printf '\nUse scripts/status_sim.sh to check status.\n'
printf 'Use scripts/stop_sim.sh to stop both processes.\n'
