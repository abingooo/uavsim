#!/usr/bin/env bash
set -euo pipefail

if [ "${1:-}" != "" ]; then
  AIRSIM_ENV="$1"
fi

AIRSIM_ENV="${AIRSIM_ENV:-/home/uav/DataDisk/PAB/AirSimPrebuilt/AirSimNH/AirSimNH.sh}"
AIRSIM_SETTINGS="${AIRSIM_SETTINGS:-/home/uav/Documents/AirSim/settings.json}"
RES_X="${RES_X:-1280}"
RES_Y="${RES_Y:-720}"
USE_NVIDIA_OFFLOAD="${USE_NVIDIA_OFFLOAD:-1}"
NVIDIA_OFFLOAD_PROVIDER="${NVIDIA_OFFLOAD_PROVIDER:-NVIDIA-G0}"
UE_GRAPHICS_ADAPTER="${UE_GRAPHICS_ADAPTER:-0}"

if [ -z "${DISPLAY:-}" ] && [ -S /tmp/.X11-unix/X0 ]; then
  export DISPLAY=:0
fi

if [ -z "${XAUTHORITY:-}" ] && [ -f /run/user/1000/gdm/Xauthority ]; then
  export XAUTHORITY=/run/user/1000/gdm/Xauthority
fi

if [ -d "$AIRSIM_ENV" ]; then
  FOUND_ENV="$(find "$AIRSIM_ENV" -maxdepth 3 -type f -name '*.sh' | sort | head -n 1)"

  if [ -z "$FOUND_ENV" ]; then
    printf 'No AirSim launcher .sh found under: %s\n' "$AIRSIM_ENV" >&2
    exit 1
  fi

  AIRSIM_ENV="$FOUND_ENV"
fi

if [ ! -f "$AIRSIM_ENV" ]; then
  printf 'AirSim prebuilt launcher not found: %s\n' "$AIRSIM_ENV" >&2
  printf 'Expected Neighborhood default path: /home/uav/DataDisk/PAB/AirSimPrebuilt/AirSimNH/AirSimNH.sh\n' >&2
  exit 1
fi

if [ ! -x "$AIRSIM_ENV" ]; then
  chmod +x "$AIRSIM_ENV"
fi

if [ "$USE_NVIDIA_OFFLOAD" = "1" ]; then
  export __NV_PRIME_RENDER_OFFLOAD=1
  export __NV_PRIME_RENDER_OFFLOAD_PROVIDER="$NVIDIA_OFFLOAD_PROVIDER"
  export __GLX_VENDOR_LIBRARY_NAME=nvidia
  export __VK_LAYER_NV_optimus=NVIDIA_only
fi

exec "$AIRSIM_ENV" -windowed -ResX="$RES_X" -ResY="$RES_Y" -graphicsadapter="$UE_GRAPHICS_ADAPTER" -settings="$AIRSIM_SETTINGS"
