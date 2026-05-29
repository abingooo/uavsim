#!/usr/bin/env bash
set -euo pipefail

pkill -f 'scripts/run_px4_sitl\.sh' || true
pkill -x px4 || true
pkill -x px4-simulator || true
