#!/usr/bin/env python3
import argparse
import csv
import math
import time
from pathlib import Path

from pymavlink import mavutil


PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6
PX4_CUSTOM_MAIN_MODE_AUTO = 4
PX4_CUSTOM_SUB_MODE_AUTO_LAND = 6

MASK_POSITION_ONLY = (
    mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
)


def px4_custom_mode(main_mode, sub_mode=0):
    return (sub_mode << 24) | (main_mode << 16)


def set_px4_custom_mode(master, main_mode, sub_mode=0):
    master.mav.set_mode_send(
        master.target_system,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
        px4_custom_mode(main_mode, sub_mode),
    )


def command_long(master, command, *params):
    values = list(params) + [0.0] * (7 - len(params))
    master.mav.command_long_send(
        master.target_system,
        master.target_component,
        command,
        0,
        *values,
    )


def send_position(master, north, east, down, yaw=0.0):
    master.mav.set_position_target_local_ned_send(
        int((time.monotonic() * 1000) % 0xFFFFFFFF),
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        MASK_POSITION_ONLY,
        north,
        east,
        down,
        0,
        0,
        0,
        0,
        0,
        0,
        yaw,
        0,
    )


def latest_position(master, timeout=0.02):
    msg = master.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=timeout)
    if not msg:
        return None
    return msg.x, msg.y, msg.z


def wait_for_local_position(master, min_samples, timeout):
    print("Waiting for local position / EKF readiness...", flush=True)
    deadline = time.monotonic() + timeout
    samples = 0
    last_pos = None

    while time.monotonic() < deadline:
        msg = master.recv_match(type="LOCAL_POSITION_NED", blocking=True, timeout=0.5)
        if not msg:
            continue

        pos = (msg.x, msg.y, msg.z)
        if all(math.isfinite(v) for v in pos):
            samples += 1
            last_pos = pos
            if samples >= min_samples:
                print(f"Local position ready: NED=({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})", flush=True)
                return last_pos
        else:
            samples = 0

    raise TimeoutError("Timed out waiting for LOCAL_POSITION_NED")


def distance_to(pos, target):
    if pos is None:
        return math.inf
    return math.sqrt(
        (pos[0] - target[0]) ** 2
        + (pos[1] - target[1]) ** 2
        + (pos[2] - target[2]) ** 2
    )


def hold_or_go(master, writer, target, duration, rate, acceptance, label):
    deadline = time.monotonic() + duration
    period = 1.0 / rate
    last_pos = None
    reached_at = None

    while time.monotonic() < deadline:
        send_position(master, *target)
        pos = latest_position(master, timeout=0.001) or last_pos
        last_pos = pos
        err = distance_to(pos, target)

        now = time.time()
        if pos:
            writer.writerow([f"{now:.3f}", label, *[f"{v:.3f}" for v in target], *[f"{v:.3f}" for v in pos], f"{err:.3f}"])
        else:
            writer.writerow([f"{now:.3f}", label, *[f"{v:.3f}" for v in target], "", "", "", ""])

        if reached_at is None and err <= acceptance:
            reached_at = time.monotonic()

        time.sleep(period)

    return last_pos


def fly_to(master, writer, target, rate, acceptance, timeout, hold, label):
    period = 1.0 / rate
    deadline = time.monotonic() + timeout
    last_pos = None

    print(f"{label}: target NED=({target[0]:.1f}, {target[1]:.1f}, {target[2]:.1f})")
    while time.monotonic() < deadline:
        send_position(master, *target)
        pos = latest_position(master, timeout=0.001) or last_pos
        last_pos = pos
        err = distance_to(pos, target)

        now = time.time()
        if pos:
            writer.writerow([f"{now:.3f}", label, *[f"{v:.3f}" for v in target], *[f"{v:.3f}" for v in pos], f"{err:.3f}"])
        else:
            writer.writerow([f"{now:.3f}", label, *[f"{v:.3f}" for v in target], "", "", "", ""])

        if err <= acceptance:
            print(f"{label}: reached, hold {hold:.1f}s")
            return hold_or_go(master, writer, target, hold, rate, acceptance, f"{label}_hold")

        time.sleep(period)

    print(f"{label}: timeout, continuing route")
    return last_pos


def main():
    parser = argparse.ArgumentParser(description="Run a small automatic low-altitude inspection route.")
    parser.add_argument("--connect", default="udpin:127.0.0.1:14030")
    parser.add_argument("--alt", default=3.0, type=float, help="flight altitude in meters")
    parser.add_argument("--length", default=8.0, type=float, help="rectangle length north in meters")
    parser.add_argument("--width", default=5.0, type=float, help="rectangle width east in meters")
    parser.add_argument("--hold", default=2.0, type=float, help="hold time at each waypoint")
    parser.add_argument("--rate", default=20.0, type=float)
    parser.add_argument("--acceptance", default=0.7, type=float)
    parser.add_argument("--timeout", default=25.0, type=float)
    parser.add_argument("--preflight-wait", default=12.0, type=float, help="extra wait after heartbeat before arming")
    parser.add_argument("--position-samples", default=20, type=int, help="local position samples required before arming")
    parser.add_argument("--log", default="")
    args = parser.parse_args()

    log_path = Path(args.log) if args.log else Path("logs") / f"inspection_route_{time.strftime('%Y%m%d_%H%M%S')}.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    route = [
        (0.0, 0.0, -args.alt),
        (args.length, 0.0, -args.alt),
        (args.length, args.width, -args.alt),
        (0.0, args.width, -args.alt),
        (0.0, 0.0, -args.alt),
    ]

    master = mavutil.mavlink_connection(args.connect)
    master.wait_heartbeat(timeout=10)
    print(f"Connected: system={master.target_system} component={master.target_component}", flush=True)
    print(f"Route log: {log_path}", flush=True)

    wait_for_local_position(master, args.position_samples, timeout=max(20.0, args.preflight_wait + 10.0))
    if args.preflight_wait > 0:
        print(f"Extra preflight wait: {args.preflight_wait:.1f}s", flush=True)
        time.sleep(args.preflight_wait)

    with log_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "stage", "target_n", "target_e", "target_d", "pos_n", "pos_e", "pos_d", "error_m"])

        print("Priming Offboard setpoints...", flush=True)
        for _ in range(int(args.rate * 2)):
            send_position(master, *route[0])
            time.sleep(1.0 / args.rate)

        command_long(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        set_px4_custom_mode(master, PX4_CUSTOM_MAIN_MODE_OFFBOARD)
        print(f"Armed and OFFBOARD requested. Route altitude: {args.alt:.1f} m", flush=True)

        for i, target in enumerate(route):
            fly_to(master, writer, target, args.rate, args.acceptance, args.timeout, args.hold, f"wp{i}")

        print("Landing...", flush=True)
        set_px4_custom_mode(master, PX4_CUSTOM_MAIN_MODE_AUTO, PX4_CUSTOM_SUB_MODE_AUTO_LAND)
        time.sleep(2)

    print("Inspection route finished.", flush=True)


if __name__ == "__main__":
    main()
