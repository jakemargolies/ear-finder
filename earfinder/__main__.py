"""
Live demo: prints head position vector to stdout at camera framerate.

    python -m earfinder           # console only
    python -m earfinder --visual  # console + annotated IR video window
    ear-finder --visual           # if installed via pip
"""

import argparse
import sys

from . import EarFinder


def main():
    parser = argparse.ArgumentParser(
        description="Stream head position (x, y, z) from a RealSense D455."
    )
    parser.add_argument(
        "--visual", "-v",
        action="store_true",
        help="Open a live annotated IR video window (press q to quit).",
    )
    args = parser.parse_args()

    print("ear-finder: streaming head position (x, y, z) in meters. Ctrl-C to stop.\n")

    try:
        with EarFinder() as ef:
            if args.visual:
                import cv2
                cv2.namedWindow("ear-finder", cv2.WINDOW_AUTOSIZE)
                for vec, frame in ef.stream_visual():
                    if vec is not None:
                        print(f"  x={vec[0]:+.3f}  y={vec[1]:+.3f}  z={vec[2]:+.3f} m", end="\r")
                    else:
                        print("  no detection                              ", end="\r")
                    cv2.imshow("ear-finder", frame)
                    if cv2.waitKey(30) & 0xFF == ord("q"):
                        break
            else:
                for vec in ef.stream():
                    if vec is not None:
                        print(f"  x={vec[0]:+.3f}  y={vec[1]:+.3f}  z={vec[2]:+.3f} m", end="\r")
                    else:
                        print("  no detection                              ", end="\r")
    except KeyboardInterrupt:
        pass
    finally:
        if args.visual:
            import cv2
            cv2.destroyAllWindows()

    print("\nstopped.")
    sys.exit(0)


if __name__ == "__main__":
    main()
