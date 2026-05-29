#!/usr/bin/env bash
set -euo pipefail

print_section() {
  printf '\n== %s ==\n' "$1"
}

print_section "Processes"
UE4_PIDS="$(pgrep -x UE4Editor || true)"
PX4_PIDS="$(pgrep -x px4 || true)"

if [ -n "$UE4_PIDS" ]; then
  ps -o pid,stat,etime,cmd -p "$(printf '%s' "$UE4_PIDS" | paste -sd, -)"
else
  printf 'UE4Editor: not running\n'
fi

if [ -n "$PX4_PIDS" ]; then
  ps -o pid,stat,etime,cmd -p "$(printf '%s' "$PX4_PIDS" | paste -sd, -)"
else
  printf 'px4: not running\n'
fi

print_section "Ports"
if command -v ss >/dev/null 2>&1; then
  ss -ltnp '( sport = :4560 or sport = :41451 or sport = :14540 or sport = :14550 or sport = :14580 )' || true
else
  printf 'ss not found.\n'
fi

print_section "Display"
if [ -z "${DISPLAY:-}" ] && [ -S /tmp/.X11-unix/X0 ]; then
  export DISPLAY=:0
fi

if [ -z "${XAUTHORITY:-}" ] && [ -f /run/user/1000/gdm/Xauthority ]; then
  export XAUTHORITY=/run/user/1000/gdm/Xauthority
fi

printf 'DISPLAY=%s\n' "${DISPLAY:-<unset>}"
printf 'XAUTHORITY=%s\n' "${XAUTHORITY:-<unset>}"
if command -v xdpyinfo >/dev/null 2>&1; then
  if xdpyinfo >/dev/null 2>&1; then
    xdpyinfo | awk '/name of display|dimensions/ {print}'
  else
    printf 'xdpyinfo could not open the current display.\n'
  fi
else
  printf 'xdpyinfo not found.\n'
fi

print_section "NVIDIA"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits || true
  printf '\nGPU processes:\n'
  nvidia-smi --query-compute-apps=pid,process_name,gpu_uuid,used_memory --format=csv,noheader || true
else
  printf 'nvidia-smi not found.\n'
fi

print_section "Recent Logs"
if ls logs/*.log >/dev/null 2>&1; then
  ls -1t logs/*.log | head -5
else
  printf 'No logs found under logs/.\n'
fi
