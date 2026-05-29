#!/usr/bin/env python3
import argparse
from io import BytesIO
import json
import math
import os
import signal
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import airsim
from PIL import Image
from pymavlink import mavutil


ROOT_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT_DIR / "logs"

PX4_CUSTOM_MAIN_MODE_OFFBOARD = 6
PX4_CUSTOM_MAIN_MODE_AUTO = 4
PX4_CUSTOM_SUB_MODE_AUTO_LAND = 6

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


def px4_custom_mode(main_mode, sub_mode=0):
    return (sub_mode << 24) | (main_mode << 16)


def pgrep(pattern):
    result = subprocess.run(
        ["pgrep", "-af", pattern],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    lines = []
    for line in result.stdout.splitlines():
        if "sim_server.py" not in line:
            lines.append(line)
    return lines


def latest_log(prefix):
    logs = sorted(LOG_DIR.glob(f"{prefix}_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(logs[0]) if logs else None


def trapezoid_progress(elapsed, distance, max_speed, acceleration):
    if distance <= 0:
        return 0.0

    max_speed = max(0.01, float(max_speed))
    acceleration = max(0.01, float(acceleration))
    ramp_time = max_speed / acceleration
    ramp_distance = 0.5 * acceleration * ramp_time**2

    if 2 * ramp_distance >= distance:
        peak_time = math.sqrt(distance / acceleration)
        total_time = 2 * peak_time
        if elapsed <= 0:
            return 0.0
        if elapsed < peak_time:
            return 0.5 * acceleration * elapsed**2
        if elapsed < total_time:
            remaining = total_time - elapsed
            return distance - 0.5 * acceleration * remaining**2
        return distance

    cruise_distance = distance - 2 * ramp_distance
    cruise_time = cruise_distance / max_speed
    total_time = 2 * ramp_time + cruise_time

    if elapsed <= 0:
        return 0.0
    if elapsed < ramp_time:
        return 0.5 * acceleration * elapsed**2
    if elapsed < ramp_time + cruise_time:
        return ramp_distance + max_speed * (elapsed - ramp_time)
    if elapsed < total_time:
        remaining = total_time - elapsed
        return distance - 0.5 * acceleration * remaining**2
    return distance


class MavlinkClient:
    def __init__(self, connect):
        self.connect = connect
        self.master = None
        self.lock = threading.RLock()
        self.rx_thread = None
        self.stop_event = threading.Event()
        self.offboard_event = threading.Event()
        self.last_heartbeat = None
        self.last_position = None
        self.last_attitude = None
        self.last_sys_status = None
        self.velocity_cmd = (0.0, 0.0, 0.0)
        self.position_cmd = None
        self.keepalive_mode = "velocity"
        self.offboard_rate = 20.0
        self.command_lock = threading.RLock()
        self.command_id = 0
        self.command_status = {
            "id": None,
            "type": None,
            "status": "idle",
            "target": None,
            "error_m": None,
            "created_at": None,
            "updated_at": None,
            "message": None,
        }

    def connected(self):
        return self.last_heartbeat is not None and (time.time() - self.last_heartbeat) < 3.0

    def ensure_started(self):
        with self.lock:
            if self.master is not None:
                return

            self.stop_event.clear()
            self.master = mavutil.mavlink_connection(self.connect)
            self.rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self.rx_thread.start()

    def wait_heartbeat(self, timeout=10.0):
        self.ensure_started()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.connected():
                return True
            time.sleep(0.1)
        return False

    def _rx_loop(self):
        while not self.stop_event.is_set():
            try:
                msg = self.master.recv_match(blocking=True, timeout=0.5)
            except Exception:
                time.sleep(0.2)
                continue

            if not msg:
                continue

            msg_type = msg.get_type()
            now = time.time()
            with self.lock:
                if msg_type == "HEARTBEAT":
                    self.last_heartbeat = now
                elif msg_type == "LOCAL_POSITION_NED":
                    self.last_position = {
                        "n": msg.x,
                        "e": msg.y,
                        "d": msg.z,
                        "vx": msg.vx,
                        "vy": msg.vy,
                        "vz": msg.vz,
                        "time": now,
                    }
                elif msg_type == "ATTITUDE":
                    self.last_attitude = {
                        "roll": msg.roll,
                        "pitch": msg.pitch,
                        "yaw": msg.yaw,
                        "rollspeed": msg.rollspeed,
                        "pitchspeed": msg.pitchspeed,
                        "yawspeed": msg.yawspeed,
                        "time": now,
                    }
                elif msg_type == "SYS_STATUS":
                    self.last_sys_status = {
                        "voltage_battery_mv": msg.voltage_battery,
                        "current_battery_ca": msg.current_battery,
                        "battery_remaining": msg.battery_remaining,
                        "time": now,
                    }

    def command_long(self, command, *params):
        self.ensure_started()
        values = list(params) + [0.0] * (7 - len(params))
        with self.lock:
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                command,
                0,
                *values,
            )

    def set_px4_custom_mode(self, main_mode, sub_mode=0):
        self.ensure_started()
        with self.lock:
            self.master.mav.set_mode_send(
                self.master.target_system,
                mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                px4_custom_mode(main_mode, sub_mode),
            )

    def send_velocity(self, vx, vy, vz):
        self.ensure_started()
        with self.lock:
            self.master.mav.set_position_target_local_ned_send(
                int((time.monotonic() * 1000) % 0xFFFFFFFF),
                self.master.target_system,
                self.master.target_component,
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

    def arm(self):
        self.command_long(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)

    def takeoff(self, altitude=3.0, timeout=30.0):
        self.wait_heartbeat(timeout=10.0)
        down = -abs(float(altitude))
        with self.lock:
            pos = self.last_position or {"n": 0.0, "e": 0.0}
            north = float(pos["n"])
            east = float(pos["e"])

        for _ in range(30):
            self.send_position(north, east, down)
            time.sleep(0.05)

        self.start_position_keepalive(north, east, down)
        self.set_px4_custom_mode(PX4_CUSTOM_MAIN_MODE_OFFBOARD)
        self.arm()

        deadline = time.time() + float(timeout)
        reached = False
        while time.time() < deadline:
            self.set_position_target(north, east, down)
            with self.lock:
                current = self.last_position
            if current and abs(float(current["d"]) - down) <= 0.5:
                reached = True
                break
            time.sleep(0.1)

        return {
            "target": {"n": north, "e": east, "d": down},
            "reached": reached,
            "position_ned": self.state().get("position_ned"),
        }

    def build_goto_target(self, north=None, east=None, down=None, altitude=None, dn=0.0, de=0.0, dd=0.0):
        if not self.wait_heartbeat(timeout=10.0):
            raise RuntimeError("MAVLink heartbeat timeout")

        with self.lock:
            current = self.last_position

        if current is None:
            raise RuntimeError("No LOCAL_POSITION_NED available")

        target_n = float(current["n"]) + float(dn) if north is None else float(north)
        target_e = float(current["e"]) + float(de) if east is None else float(east)

        if altitude is not None:
            target_d = -abs(float(altitude))
        elif down is None:
            target_d = float(current["d"]) + float(dd)
        else:
            target_d = float(down)

        return target_n, target_e, target_d

    def goto_async(
        self,
        north=None,
        east=None,
        down=None,
        altitude=None,
        dn=0.0,
        de=0.0,
        dd=0.0,
        timeout=30.0,
        acceptance=0.5,
        speed=None,
        acceleration=None,
    ):
        target = self.build_goto_target(north, east, down, altitude, dn, de, dd)
        speed_mps = None if speed is None else max(0.0, float(speed))
        acceleration_mps2 = None
        if speed_mps and speed_mps > 0:
            acceleration_mps2 = max(0.05, float(acceleration if acceleration is not None else 0.5))
        now = time.time()

        with self.command_lock:
            self.command_id += 1
            command_id = self.command_id
            self.command_status = {
                "id": command_id,
                "type": "goto",
                "status": "active",
                "target": {"n": target[0], "e": target[1], "d": target[2]},
                "error_m": None,
                "created_at": now,
                "updated_at": now,
                "timeout": float(timeout),
                "acceptance": float(acceptance),
                "speed_mps": speed_mps,
                "acceleration_mps2": acceleration_mps2,
                "setpoint": None,
                "message": "goto accepted",
            }

        threading.Thread(
            target=self._goto_worker,
            args=(command_id, target, float(timeout), float(acceptance), speed_mps, acceleration_mps2),
            daemon=True,
        ).start()

        return self.current_command()

    def _goto_worker(self, command_id, target, timeout, acceptance, speed_mps=None, acceleration_mps2=None):
        target_n, target_e, target_d = target

        start = None
        if speed_mps and speed_mps > 0:
            with self.lock:
                pos = self.last_position
            if pos:
                start = (float(pos["n"]), float(pos["e"]), float(pos["d"]))

        first_setpoint = start if start is not None else target
        for _ in range(20):
            if not self.command_is_active(command_id):
                return
            self.send_position(*first_setpoint)
            time.sleep(0.05)

        self.start_position_keepalive(*first_setpoint)
        self.set_px4_custom_mode(PX4_CUSTOM_MAIN_MODE_OFFBOARD)

        distance = None
        direction = None
        started_at = time.time()
        if start is not None:
            dn = target_n - start[0]
            de = target_e - start[1]
            dd = target_d - start[2]
            distance = math.sqrt(dn**2 + de**2 + dd**2)
            if distance > 0.001:
                direction = (dn / distance, de / distance, dd / distance)

        deadline = time.time() + float(timeout)
        reached = False
        last_error = None
        while time.time() < deadline:
            if not self.command_is_active(command_id):
                return

            if direction is not None and speed_mps and speed_mps > 0 and acceleration_mps2:
                elapsed = time.time() - started_at
                travel = min(distance, trapezoid_progress(elapsed, distance, speed_mps, acceleration_mps2))
                setpoint = (
                    start[0] + direction[0] * travel,
                    start[1] + direction[1] * travel,
                    start[2] + direction[2] * travel,
                )
            else:
                setpoint = target

            self.set_position_target(*setpoint)
            with self.lock:
                pos = self.last_position

            if pos:
                last_error = math.sqrt(
                    (float(pos["n"]) - target_n) ** 2
                    + (float(pos["e"]) - target_e) ** 2
                    + (float(pos["d"]) - target_d) ** 2
                )
                self.update_command(
                    command_id,
                    status="active",
                    error_m=last_error,
                    setpoint={"n": setpoint[0], "e": setpoint[1], "d": setpoint[2]},
                    message="goto running",
                )
                if last_error <= float(acceptance):
                    reached = True
                    break
            time.sleep(0.1)

        if reached:
            self.update_command(command_id, status="reached", error_m=last_error, message="target reached")
        else:
            self.update_command(command_id, status="timeout", error_m=last_error, message="goto timeout")

    def command_is_active(self, command_id):
        with self.command_lock:
            return self.command_status.get("id") == command_id and self.command_status.get("status") == "active"

    def update_command(self, command_id, **updates):
        with self.command_lock:
            if self.command_status.get("id") != command_id:
                return
            self.command_status.update(updates)
            self.command_status["updated_at"] = time.time()

    def current_command(self):
        with self.command_lock:
            status = dict(self.command_status)
        with self.lock:
            status["position_ned"] = self.last_position
        return status

    def stop_current_command(self):
        with self.command_lock:
            previous_id = self.command_status.get("id")
            now = time.time()
            self.command_id += 1
            self.command_status = {
                "id": self.command_id,
                "type": "stop",
                "status": "stopped",
                "target": None,
                "error_m": None,
                "created_at": now,
                "updated_at": now,
                "message": f"canceled command {previous_id}",
            }

        with self.lock:
            current = self.last_position

        if current:
            self.start_position_keepalive(float(current["n"]), float(current["e"]), float(current["d"]))
            self.set_px4_custom_mode(PX4_CUSTOM_MAIN_MODE_OFFBOARD)
        else:
            self.start_offboard_keepalive(0.0, 0.0, 0.0)

        return self.current_command()

    def send_position(self, north, east, down, yaw=0.0):
        mask = (
            mavutil.mavlink.POSITION_TARGET_TYPEMASK_VX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_VZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AX_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AY_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_AZ_IGNORE
            | mavutil.mavlink.POSITION_TARGET_TYPEMASK_YAW_RATE_IGNORE
        )
        self.ensure_started()
        with self.lock:
            self.master.mav.set_position_target_local_ned_send(
                int((time.monotonic() * 1000) % 0xFFFFFFFF),
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_FRAME_LOCAL_NED,
                mask,
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

    def land(self):
        self.cancel_command("landing")
        self.set_px4_custom_mode(PX4_CUSTOM_MAIN_MODE_AUTO, PX4_CUSTOM_SUB_MODE_AUTO_LAND)
        self.stop_offboard_keepalive()

    def start_offboard_keepalive(self, vx, vy, vz):
        with self.lock:
            self.velocity_cmd = (float(vx), float(vy), float(vz))
            self.keepalive_mode = "velocity"
        if self.offboard_event.is_set():
            return
        self.offboard_event.set()
        threading.Thread(target=self._offboard_loop, daemon=True).start()

    def start_position_keepalive(self, north, east, down):
        with self.lock:
            self.position_cmd = (float(north), float(east), float(down))
            self.keepalive_mode = "position"
        if self.offboard_event.is_set():
            return
        self.offboard_event.set()
        threading.Thread(target=self._offboard_loop, daemon=True).start()

    def set_position_target(self, north, east, down):
        with self.lock:
            self.position_cmd = (float(north), float(east), float(down))
            self.keepalive_mode = "position"

    def stop_offboard_keepalive(self):
        self.offboard_event.clear()

    def _offboard_loop(self):
        period = 1.0 / self.offboard_rate
        while self.offboard_event.is_set():
            with self.lock:
                vx, vy, vz = self.velocity_cmd
                position_cmd = self.position_cmd
                mode = self.keepalive_mode
            try:
                if mode == "position" and position_cmd is not None:
                    self.send_position(*position_cmd)
                else:
                    self.send_velocity(vx, vy, vz)
            except Exception:
                pass
            time.sleep(period)

    def velocity_for(self, vx, vy, vz, duration):
        self.wait_heartbeat(timeout=10.0)
        self.cancel_command("velocity command")
        self.set_px4_custom_mode(PX4_CUSTOM_MAIN_MODE_OFFBOARD)
        with self.lock:
            self.velocity_cmd = (float(vx), float(vy), float(vz))
            self.keepalive_mode = "velocity"
        self.start_offboard_keepalive(vx, vy, vz)

        if duration and float(duration) > 0:
            time.sleep(float(duration))
            with self.lock:
                self.velocity_cmd = (0.0, 0.0, 0.0)

    def cancel_command(self, message):
        with self.command_lock:
            if self.command_status.get("status") == "active":
                self.command_status["status"] = "canceled"
                self.command_status["updated_at"] = time.time()
                self.command_status["message"] = message

    def state(self):
        command = self.current_command()
        with self.lock:
            return {
                "connected": self.connected(),
                "heartbeat_age_s": None if self.last_heartbeat is None else round(time.time() - self.last_heartbeat, 3),
                "position_ned": self.last_position,
                "attitude": self.last_attitude,
                "sys_status": self.last_sys_status,
                "offboard_keepalive": self.offboard_event.is_set(),
                "keepalive_mode": self.keepalive_mode,
                "position_cmd_ned": self.position_cmd,
                "velocity_cmd_body_ned": self.velocity_cmd,
                "command": command,
            }


class SimManager:
    def __init__(self, mavlink_client):
        self.mavlink = mavlink_client
        self.lock = threading.RLock()
        self.launch_process = None
        self.last_start_output = ""

    def running(self):
        return {
            "px4": pgrep(r"(^|/)px4($| )"),
            "airsim": pgrep(r"/AirSimNH/Binaries/Linux/AirSimNH|UE4Editor .*Blocks\.uproject"),
            "qgc_udp_sink": pgrep(r"scripts/qgc_udp_sink.py"),
        }

    def is_running(self):
        status = self.running()
        return bool(status["px4"] or status["airsim"])

    def start(self, wait=True, timeout=90):
        with self.lock:
            if self.is_running():
                return {"started": False, "reason": "already_running", "status": self.status()}

            env = os.environ.copy()
            env.update(
                {
                    "START_QGC_UDP_SINK": "1",
                    "AIRSIM_LAUNCHER": str(ROOT_DIR / "scripts" / "run_neighborhood.sh"),
                    "AIRSIM_NAME": "AirSimNH",
                }
            )
            proc = subprocess.run(
                [str(ROOT_DIR / "scripts" / "run_sim.sh")],
                cwd=ROOT_DIR,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=20,
                check=False,
            )
            self.last_start_output = proc.stdout
            if proc.returncode != 0:
                return {"started": False, "returncode": proc.returncode, "output": proc.stdout, "status": self.status()}

        result = {"started": True, "output": self.last_start_output, "status": self.status()}
        if wait:
            result["ready"] = self.wait_ready(timeout=timeout)
            result["status"] = self.status()
        return result

    def stop(self):
        self.mavlink.stop_offboard_keepalive()
        proc = subprocess.run(
            [str(ROOT_DIR / "scripts" / "stop_sim.sh")],
            cwd=ROOT_DIR,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        return {"stopped": proc.returncode == 0, "returncode": proc.returncode, "output": proc.stdout, "status": self.status()}

    def wait_ready(self, timeout=90):
        deadline = time.time() + timeout
        while time.time() < deadline:
            px4_log = latest_log("px4")
            airsim_log = latest_log("airsim")
            px4_ok = px4_log and "Simulator connected on TCP port 4560" in Path(px4_log).read_text(errors="ignore")
            airsim_ok = airsim_log and "Connected to SITL over TCP." in Path(airsim_log).read_text(errors="ignore")
            if px4_ok and airsim_ok:
                self.mavlink.wait_heartbeat(timeout=8)
                return True
            time.sleep(1.0)
        return False

    def status(self):
        return {
            "running": self.running(),
            "logs": {
                "px4": latest_log("px4"),
                "airsim": latest_log("airsim"),
                "qgc_udp_sink": latest_log("qgc_udp_sink"),
            },
            "mavlink": self.mavlink.state(),
        }


class AirSimCameraClient:
    def __init__(self, host="127.0.0.1", port=41451):
        self.host = host
        self.port = port
        self.lock = threading.RLock()
        self.client = None

    def ensure_connected(self):
        with self.lock:
            if self.client is None:
                self.client = airsim.MultirotorClient(ip=self.host, port=self.port)
                self.client.confirmConnection()
            return self.client

    def reset_connection_locked(self):
        self.client = None

    def sim_get_images_locked(self, camera, vehicle_name):
        client = self.ensure_connected()
        return client.simGetImages(
            [airsim.ImageRequest(str(camera), airsim.ImageType.Scene, False, True)],
            vehicle_name=vehicle_name,
        )

    def get_scene_png(self, camera="0", vehicle_name="PX4"):
        with self.lock:
            try:
                responses = self.sim_get_images_locked(camera, vehicle_name)
            except Exception:
                self.reset_connection_locked()
                responses = self.sim_get_images_locked(camera, vehicle_name)
        if not responses:
            raise RuntimeError("AirSim returned no image responses")
        response = responses[0]
        data = bytes(response.image_data_uint8)
        if not data:
            raise RuntimeError("AirSim returned empty image data")
        return {
            "data": data,
            "width": response.width,
            "height": response.height,
            "camera": str(camera),
            "vehicle_name": vehicle_name,
            "time": time.time(),
        }

    def get_scene_jpeg(self, camera="0", vehicle_name="PX4", quality=80):
        image = self.get_scene_png(camera=camera, vehicle_name=vehicle_name)
        source = Image.open(BytesIO(image["data"]))
        if source.mode != "RGB":
            source = source.convert("RGB")
        output = BytesIO()
        source.save(output, format="JPEG", quality=int(quality), optimize=True)
        image["data"] = output.getvalue()
        image["format"] = "jpeg"
        return image


class SimRequestHandler(BaseHTTPRequestHandler):
    manager = None
    mavlink = None
    camera = None

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body else {}

    def write_json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def write_binary(self, status, content_type, data, extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, str(value))
        self.end_headers()
        self.wfile.write(data)

    def write_camera_stream(self, query):
        camera = query.get("camera", ["0"])[0]
        vehicle_name = query.get("vehicle", ["PX4"])[0]
        fps = max(1.0, min(float(query.get("fps", ["10"])[0]), 30.0))
        quality = max(1, min(int(query.get("quality", ["80"])[0]), 95))
        period = 1.0 / fps

        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        while True:
            started_at = time.time()
            image = self.camera.get_scene_jpeg(
                camera=camera,
                vehicle_name=vehicle_name,
                quality=quality,
            )
            header = (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(image['data'])}\r\n".encode("ascii")
                + f"X-Image-Width: {image['width']}\r\n".encode("ascii")
                + f"X-Image-Height: {image['height']}\r\n".encode("ascii")
                + b"\r\n"
            )
            try:
                self.wfile.write(header)
                self.wfile.write(image["data"])
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                break

            delay = period - (time.time() - started_at)
            if delay > 0:
                time.sleep(delay)

    def get_camera_info(self, query):
        image = self.camera.get_scene_png(
            camera=query.get("camera", ["0"])[0],
            vehicle_name=query.get("vehicle", ["PX4"])[0],
        )
        self.write_json(
            200,
            {
                "ok": True,
                "width": image["width"],
                "height": image["height"],
                "camera": image["camera"],
                "vehicle_name": image["vehicle_name"],
                "time": image["time"],
                "bytes": len(image["data"]),
            },
        )

    def get_camera_scene_png(self, query):
        image = self.camera.get_scene_png(
            camera=query.get("camera", ["0"])[0],
            vehicle_name=query.get("vehicle", ["PX4"])[0],
        )
        self.write_binary(
            200,
            "image/png",
            image["data"],
            {
                "X-Image-Width": image["width"],
                "X-Image-Height": image["height"],
                "X-Camera": image["camera"],
                "X-Vehicle-Name": image["vehicle_name"],
            },
        )

    def post_takeoff(self, payload):
        altitude = float(payload.get("altitude", 3.0))
        timeout = float(payload.get("timeout", 30.0))
        result = self.mavlink.takeoff(altitude=altitude, timeout=timeout)
        self.write_json(200, {"ok": result["reached"], "altitude": altitude, **result})

    def post_velocity(self, payload):
        vx = float(payload.get("vx", 0.0))
        vy = float(payload.get("vy", 0.0))
        vz = float(payload.get("vz", 0.0))
        duration = float(payload.get("duration", 0.0))
        self.mavlink.velocity_for(vx, vy, vz, duration)
        self.write_json(200, {"ok": True, "vx": vx, "vy": vy, "vz": vz, "duration": duration})

    def post_goto(self, payload):
        result = self.mavlink.goto_async(
            north=payload.get("n"),
            east=payload.get("e"),
            down=payload.get("d"),
            altitude=payload.get("altitude"),
            dn=float(payload.get("dn", 0.0)),
            de=float(payload.get("de", 0.0)),
            dd=float(payload.get("dd", 0.0)),
            timeout=float(payload.get("timeout", 30.0)),
            acceptance=float(payload.get("acceptance", 0.5)),
            speed=payload.get("speed"),
            acceleration=payload.get("acceleration"),
        )
        self.write_json(200, {"ok": True, **result})

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        try:
            if path == "/health":
                self.mavlink.ensure_started()
                self.write_json(200, {"ok": True, "mavlink_connected": self.mavlink.connected()})
            elif path == "/uav/state":
                self.mavlink.ensure_started()
                self.write_json(200, self.mavlink.state())
            elif path == "/uav/cmd/current":
                self.mavlink.ensure_started()
                self.write_json(200, self.mavlink.current_command())
            elif path == "/uav/camera/info":
                self.get_camera_info(query)
            elif path == "/uav/camera/scene.png":
                self.get_camera_scene_png(query)
            elif path == "/uav/camera/stream.mjpg":
                self.write_camera_stream(query)
            elif path == "/sim/status":
                self.write_json(200, self.manager.status())
            else:
                self.write_json(404, {"error": "not_found", "path": path})
        except Exception as exc:
            self.write_json(500, {"error": type(exc).__name__, "message": str(exc)})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/sim/start":
                wait = bool(payload.get("wait", True))
                timeout = float(payload.get("timeout", 90))
                self.write_json(200, self.manager.start(wait=wait, timeout=timeout))
            elif path == "/sim/stop":
                self.write_json(200, self.manager.stop())
            elif path == "/uav/arm":
                self.mavlink.wait_heartbeat(timeout=10)
                self.mavlink.arm()
                self.write_json(200, {"ok": True})
            elif path == "/uav/takeoff":
                self.post_takeoff(payload)
            elif path == "/uav/land":
                self.mavlink.land()
                self.write_json(200, {"ok": True})
            elif path == "/uav/cmd/velocity":
                self.post_velocity(payload)
            elif path == "/uav/cmd/goto":
                self.post_goto(payload)
            elif path == "/uav/cmd/stop":
                result = self.mavlink.stop_current_command()
                self.write_json(200, {"ok": True, **result})
            else:
                self.write_json(404, {"error": "not_found", "path": path})
        except Exception as exc:
            self.write_json(500, {"error": type(exc).__name__, "message": str(exc)})


def main():
    parser = argparse.ArgumentParser(description="Local HTTP service for PX4 + AirSimNH simulation.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18080, type=int)
    parser.add_argument("--connect", default="udpin:127.0.0.1:14030")
    args = parser.parse_args()

    mavlink = MavlinkClient(args.connect)
    manager = SimManager(mavlink)
    camera = AirSimCameraClient()
    SimRequestHandler.mavlink = mavlink
    SimRequestHandler.manager = manager
    SimRequestHandler.camera = camera

    server = ThreadingHTTPServer((args.host, args.port), SimRequestHandler)
    print(f"sim_server listening on http://{args.host}:{args.port}")

    def shutdown(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("sim_server shutting down")
    finally:
        server.server_close()
        mavlink.stop_offboard_keepalive()


if __name__ == "__main__":
    main()
