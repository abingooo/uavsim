#!/usr/bin/env python3
import argparse
import select
import sys
import termios
import time
import tty

from pymavlink import mavutil


MASK_VEL_ONLY = (
    mavutil.mavlink.POSITION_TARGET_TYPEMASK_X_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Y_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_Z_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_IGNORE
    | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
)


def read_key(timeout):
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if ready:
        return sys.stdin.read(1)
    return None


PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6
PX4_CUSTOM_MAIN_MODE_AUTO = 4
PX4_CUSTOM_SUB_MODE_AUTO_LAND = 6


def px4_custom_mode(main_mode, sub_mode=0):
    return (sub_mode << 24) | (main_mode << 16)


def send_position(master, x, y, z, yaw=0.0):
    mask = (
        mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
        | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
    )
    master.mav.set_position_target_local_ned_send(
        int((time.monotonic() * 1000) % 0xFFFFFFFF),
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_LOCAL_NED,
        mask,
        x,
        y,
        z,
        0,
        0,
        0,
        0,
        0,
        0,
        yaw,
        0,
    )


def send_velocity(master, vx, vy, vz):
    master.mav.set_position_target_local_ned_send(
        int((time.monotonic() * 1000) % 0xFFFFFFFF),
        master.target_system,
        master.target_component,
        mavutil.mavlink.MAV_FRAME_BODY_NED,
        MASK_VEL_ONLY,
        0,
        0,
        0,
        vx,
        vy,
        vz,
        0,
        0,
        0,
        0,
        0,
    )


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


def arm(master):
    command_long(master, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)


def land(master):
    set_px4_custom_mode(master, PX4_CUSTOM_MAIN_MODE_AUTO, PX4_CUSTOM_SUB_MODE_AUTO_LAND)


def main():
    parser = argparse.ArgumentParser(description="Keyboard velocity control for PX4 SITL over MAVLink.")
    parser.add_argument("--connect", default="udpin:127.0.0.1:14030")
    parser.add_argument("--speed", default=1.0, type=float, help="horizontal speed in m/s")
    parser.add_argument("--vertical-speed", default=0.5, type=float, help="vertical speed in m/s")
    parser.add_argument("--rate", default=20.0, type=float, help="setpoint rate in Hz")
    parser.add_argument("--takeoff-alt", default=3.0, type=float, help="takeoff altitude in meters")
    args = parser.parse_args()

    master = mavutil.mavlink_connection(args.connect)
    master.wait_heartbeat(timeout=10)
    print(f"Connected: system={master.target_system} component={master.target_component}")

    print("Sending initial Offboard setpoints...")
    for _ in range(30):
        send_position(master, 0.0, 0.0, -args.takeoff_alt)
        time.sleep(0.05)

    arm(master)
    set_px4_custom_mode(master, PX4_CUSTOM_MAIN_MODE_OFFBOARD)
    print(f"Armed and OFFBOARD requested. Climbing to {args.takeoff_alt:.1f} m...")

    for _ in range(int(args.rate * 6)):
        send_position(master, 0.0, 0.0, -args.takeoff_alt)
        time.sleep(1.0 / args.rate)

    print("Controls: w/s forward/back, a/d left/right, r/f up/down, space stop, l land, q quit")

    old_term = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    period = 1.0 / args.rate
    vx = vy = vz = 0.0

    try:
        while True:
            key = read_key(period)
            if key:
                if key == "w":
                    vx, vy, vz = args.speed, 0.0, 0.0
                elif key == "s":
                    vx, vy, vz = -args.speed, 0.0, 0.0
                elif key == "a":
                    vx, vy, vz = 0.0, -args.speed, 0.0
                elif key == "d":
                    vx, vy, vz = 0.0, args.speed, 0.0
                elif key == "r":
                    vx, vy, vz = 0.0, 0.0, -args.vertical_speed
                elif key == "f":
                    vx, vy, vz = 0.0, 0.0, args.vertical_speed
                elif key == " ":
                    vx = vy = vz = 0.0
                elif key == "l":
                    land(master)
                    print("\nLand requested.")
                elif key == "q":
                    vx = vy = vz = 0.0
                    send_velocity(master, vx, vy, vz)
                    break

            send_velocity(master, vx, vy, vz)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_term)
        print("\nStopped keyboard control.")


if __name__ == "__main__":
    main()
