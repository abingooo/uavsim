#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AIRSIM_ENV="${AIRSIM_ENV:-/home/uav/DataDisk/PAB/AirSimPrebuilt/AirSimNH}"

exec "$ROOT_DIR/scripts/run_prebuilt_env.sh" "$AIRSIM_ENV"
