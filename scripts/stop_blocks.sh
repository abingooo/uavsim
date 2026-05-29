#!/usr/bin/env bash
set -euo pipefail

pkill -f 'UE4Editor .*Blocks\.uproject' || true
pkill -f 'UE4Editor .*LowAltitudeInspection\.uproject' || true
pkill -f '/AirSimNH/Binaries/Linux/AirSimNH' || true
pkill -f '/Blocks/Binaries/Linux/Blocks' || true
