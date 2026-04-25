"""
Live demo: prints head position vector to stdout at camera framerate.

    python -m earfinder
    ear-finder          # if installed via pip
"""

import signal
import sys

from . import EarFinder


def main():
    print("ear-finder: streaming head position (x, y, z) in meters. Ctrl-C to stop.\n")

    def _shutdown(sig, frame):
        print("\nstopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)

    with EarFinder() as ef:
        for vec in ef.stream():
            if vec is not None:
                print(f"  x={vec[0]:+.3f}  y={vec[1]:+.3f}  z={vec[2]:+.3f} m", end="\r")
            else:
                print("  no detection                              ", end="\r")


if __name__ == "__main__":
    main()
