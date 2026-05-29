#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SETTINGS = ROOT_DIR / "configs" / "settings_px4_sitl.json"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser(
        description="Set PX4 vehicle initial spawn pose in AirSim settings template."
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS), help="AirSim settings template path")
    parser.add_argument("--vehicle", default="PX4", help="Vehicle name in settings.json")
    parser.add_argument("--x", type=float, help="Initial X/North position in meters")
    parser.add_argument("--y", type=float, help="Initial Y/East position in meters")
    parser.add_argument("--z", type=float, help="Initial Z/Down position in meters; negative is above ground")
    parser.add_argument("--yaw", type=float, help="Initial yaw heading in degrees")
    parser.add_argument("--pitch", type=float, help="Initial pitch in degrees")
    parser.add_argument("--roll", type=float, help="Initial roll in degrees")
    parser.add_argument("--install", action="store_true", help="Install updated template to ~/Documents/AirSim/settings.json")
    args = parser.parse_args()

    settings_path = Path(args.settings).expanduser().resolve()
    data = load_json(settings_path)

    vehicles = data.setdefault("Vehicles", {})
    if args.vehicle not in vehicles:
        raise SystemExit(f"Vehicle not found in settings: {args.vehicle}")

    vehicle = vehicles[args.vehicle]
    updates = {
        "X": args.x,
        "Y": args.y,
        "Z": args.z,
        "Yaw": args.yaw,
        "Pitch": args.pitch,
        "Roll": args.roll,
    }

    changed = False
    for key, value in updates.items():
        if value is not None:
            vehicle[key] = value
            changed = True

    if changed:
        save_json(settings_path, data)

    pose = {key: vehicle.get(key, 0.0) for key in ("X", "Y", "Z", "Yaw", "Pitch", "Roll")}
    action = "Updated" if changed else "Current"
    print(f"{action} {args.vehicle} spawn pose in {settings_path}:")
    print(json.dumps(pose, indent=2, ensure_ascii=False))

    if args.install:
        subprocess.run([str(ROOT_DIR / "scripts" / "install_settings.sh"), str(settings_path)], check=True)


if __name__ == "__main__":
    main()
