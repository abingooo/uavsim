#!/usr/bin/env python3
import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description="Discard MAVLink UDP packets sent to a local QGC port.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=14550, type=int)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"Listening on udp://{args.host}:{args.port}", flush=True)

    while True:
        sock.recvfrom(65535)


if __name__ == "__main__":
    main()
