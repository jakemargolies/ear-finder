"""
netbridge — relay head position from earfinder to MATLAB over UDP loopback.

Reads config/room.toml for the destination port, then streams 12-byte
little-endian float32[x, y, z] packets to 127.0.0.1:port_matlab at the
camera framerate (~30 Hz), skipping frames where no person is detected.

Usage:
    python -m netbridge
    python -m netbridge --config path/to/room.toml
"""

import argparse
import socket
import struct
import sys
import tomllib

from earfinder import EarFinder


def main():
    parser = argparse.ArgumentParser(description="Relay earfinder positions to MATLAB via UDP.")
    parser.add_argument("--config", default="config/room.toml")
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        cfg = tomllib.load(f)

    port = cfg["network"]["port_matlab"]
    dest = ("127.0.0.1", port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"netbridge: streaming head position to {dest[0]}:{dest[1]}  (Ctrl-C to stop)\n")

    try:
        with EarFinder() as ef:
            for vec in ef.stream():
                if vec is None:
                    continue
                sock.sendto(struct.pack("<3f", *vec), dest)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()

    print("\nnetbridge: stopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
