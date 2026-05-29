#!/usr/bin/env bash
set -euo pipefail

AIRSIM_DIR="${AIRSIM_DIR:-/home/uav/DataDisk/PAB/AirSim}"
UE4_EDITOR="${UE4_EDITOR:-/home/uav/DataDisk/PAB/UnrealEngine/Engine/Binaries/Linux/UE4Editor}"
BLOCKS_PROJECT="${BLOCKS_PROJECT:-$AIRSIM_DIR/Unreal/Environments/Blocks 4.27/Blocks.uproject}"
MAP="${MAP:-/Game/FlyingCPP/Maps/FlyingExampleMap}"
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

if [ ! -x "$UE4_EDITOR" ]; then
  printf 'UE4Editor not executable: %s\n' "$UE4_EDITOR" >&2
  exit 1
fi

if [ ! -f "$BLOCKS_PROJECT" ]; then
  printf 'Blocks project not found: %s\n' "$BLOCKS_PROJECT" >&2
  exit 1
fi

if [ "$USE_NVIDIA_OFFLOAD" = "1" ]; then
  export __NV_PRIME_RENDER_OFFLOAD=1
  export __NV_PRIME_RENDER_OFFLOAD_PROVIDER="$NVIDIA_OFFLOAD_PROVIDER"
  export __GLX_VENDOR_LIBRARY_NAME=nvidia
  export __VK_LAYER_NV_optimus=NVIDIA_only
fi

exec "$UE4_EDITOR" "$BLOCKS_PROJECT" "$MAP" -game -windowed -ResX="$RES_X" -ResY="$RES_Y" -graphicsadapter="$UE_GRAPHICS_ADAPTER"
