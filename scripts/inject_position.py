#!/usr/bin/env python3
"""
inject_position.py — send fake head position packets to the MATLAB UDP port.

Simulates what netbridge will do in production.  Use this to test
test_udp_rx.m (or beam_client.m) without running earfinder.

Usage:
    python scripts/inject_position.py              # slow sweep, 10 Hz
    python scripts/inject_position.py --hz 30      # match camera framerate
    python scripts/inject_position.py --static 0.0 0.0 2.0   # fixed position

Payload: 12 bytes, little-endian float32[3] = [x, y, z] in meters.
Destination: 127.0.0.1:5007
"""

import argparse
import math
import socket
import struct
import time


def main():
    parser = argparse.ArgumentParser(description="Inject fake head positions via UDP loopback.")
    parser.add_argument("--port", type=int, default=5007)
    parser.add_argument("--hz",   type=float, default=10.0, help="Send rate in Hz")
    parser.add_argument("--static", nargs=3, type=float, metavar=("X","Y","Z"),
                        help="Send a fixed position instead of sweeping")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dest = ("127.0.0.1", args.port)
    interval = 1.0 / args.hz

    print(f"inject_position: sending to {dest[0]}:{dest[1]} at {args.hz} Hz  (Ctrl-C to stop)\n")

    t = 0.0
    while True:
        if args.static:
            x, y, z = args.static
        else:
            # Gentle figure-8 sweep at ~1 m distance: x oscillates, z constant
            x = 0.3 * math.sin(t)
            y = 0.1
            z = 1.5 + 0.2 * math.sin(2 * t)

        payload = struct.pack("<3f", x, y, z)
        sock.sendto(payload, dest)
        print(f"  sent  x={x:+.3f}  y={y:+.3f}  z={z:+.3f} m")

        t += interval
        time.sleep(interval)


if __name__ == "__main__":
    main()
