# ear-finder

Locates a person's head in 3D space using an Intel RealSense D455 and MediaPipe Pose. Returns the XYZ displacement from the camera to the midpoint between the subject's ears; intended as a target for acoustic beam steering.

```
x = right  |  y = down  |  z = forward  |  units = meters
```

---

## macOS / Apple Silicon notes

Several macOS-specific constraints shaped this setup:

- **Color camera is inaccessible via libusb.** macOS's UVC kernel driver claims the D455 color camera exclusively and cannot be displaced. This module uses the **left infrared (IR) stream** instead b/c it's on the same USB interface as depth, requires no special permissions, and is already synchronized and aligned with the depth frame.
- **pyrealsense2 is not pip-installable on macOS arm64** and must be built from source with `-DFORCE_RSUSB_BACKEND=ON`.
- **USB 3.0 cable required.** USB-C cables can be limited to USB 2.0 speeds, which prevents the depth stream from working. Use a cable rated USB 3.1 Gen 1 or better.
- **No sudo required.** The IR and depth streams on the D455 are not UVC devices, so macOS does not block them.
- **mediapipe ≥ 0.10 drops the legacy `solutions` API** on macOS arm64. This module uses the Tasks API with a downloaded model file.

---

## Requirements

- Apple Silicon Mac (M1/M2/M3 or later)
- macOS Ventura or later
- Intel RealSense D455
- USB-C cable rated USB 3.1 Gen 1 or better
- Python 3.11 (via `uv`)
- Homebrew

---

## Installation

### 1. Install system dependencies

```bash
brew install librealsense cmake uv
```

### 2. Clone and set up the project

```bash
git clone <repo-url>
cd ear-finder
uv sync --extra dev
```

### 3. Build pyrealsense2 from source

The Homebrew `librealsense` package does not include Python bindings. Build them manually:

```bash
git clone --depth 1 -b v2.57.7 https://github.com/IntelRealSense/librealsense /tmp/librealsense-src
mkdir /tmp/librealsense-build && cd /tmp/librealsense-build

cmake /tmp/librealsense-src \
  -DBUILD_PYTHON_BINDINGS=ON \
  -DBUILD_EXAMPLES=OFF \
  -DBUILD_GRAPHICAL_EXAMPLES=OFF \
  -DCMAKE_BUILD_TYPE=Release \
  -DFORCE_RSUSB_BACKEND=ON \
  -DPYTHON_EXECUTABLE=$(which python3.11)

make -j$(sysctl -n hw.logicalcpu) pyrealsense2
```

> **`-DFORCE_RSUSB_BACKEND=ON` is required.** Without it, libusb cannot claim any USB interface on the D455 under macOS's security model.

Copy the built binding into the virtualenv:

```bash
cp /tmp/librealsense-build/Release/pyrealsense2.cpython-311-darwin.so \
  /path/to/ear-finder/.venv/lib/python3.11/site-packages/
```

### 4. Download the MediaPipe pose model

```bash
cd /path/to/ear-finder
curl -L -o pose_landmarker.task \
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
```

---

## Verify the camera

Plug in the D455 with a USB 3.1+ cable, then:

```bash
sudo /opt/homebrew/bin/rs-enumerate-devices
```

You should see `Usb Type Descriptor: 3.x` and a full list of stream profiles. If it shows `2.1`, the cable is USB 2.0 — replace it.

---

## Running

### Console output

Streams `x / y / z` to the terminal at ~30 Hz:

```bash
python -m earfinder
```

```
ear-finder: streaming head position (x, y, z) in meters. Ctrl-C to stop.

  x=+0.042  y=+0.115  z=+1.203 m
```

### Visual mode

Opens a live IR video window with landmarks overlaid. **Must be run from a terminal**, not from the VS Code debugpy launcher (which blocks window rendering):

```bash
python -m earfinder --visual
```

The window shows a grayscale infrared image — the IR projector dot pattern is blurred out before MediaPipe sees it. Press `q` to quit.

| Indicator | Meaning |
|---|---|
| Cyan dots | Left and right ear landmarks |
| Cyan line | Connection between ears |
| Green circle + crosshair | Head midpoint — the reported 3D position |
| Green text | `x / y / z` in meters |
| Orange text | Pose detected but depth unavailable at midpoint |
| Red text | No person detected |

---

## VS Code debugging

Two launch configurations are provided in `.vscode/launch.json`:

- **ear-finder: console** — runs `python -m earfinder` with full debugger support and breakpoints
- **ear-finder: attach (sudo)** — attach debugger to a process started manually in a terminal (useful if you ever need root access for other stream types)

> **Visual mode via VS Code:** The `cv2.imshow` window will not appear when launched through VS Code's debugpy launcher. Run `--visual` directly from a terminal instead.

---

## Python API

```python
from earfinder import EarFinder

# Single snapshot
with EarFinder() as ef:
    vec = ef.get_head_vector()
    if vec is not None:
        print(f"x={vec[0]:.3f}  y={vec[1]:.3f}  z={vec[2]:.3f}")

# Continuous stream
with EarFinder() as ef:
    for vec in ef.stream():
        if vec is not None:
            print(vec)  # np.ndarray [x, y, z] in meters

# Continuous stream with annotated IR frames
with EarFinder() as ef:
    for vec, frame in ef.stream_visual():
        cv2.imshow("head", frame)
        cv2.waitKey(30)
```

### `EarFinder` constructor options

| Parameter | Default | Description |
|---|---|---|
| `serial` | `None` | RealSense device serial number (for multi-camera setups) |
| `width` | `848` | Stream width in pixels |
| `height` | `480` | Stream height in pixels |
| `fps` | `30` | Frame rate |
| `model_path` | `pose_landmarker.task` | Path to MediaPipe pose landmarker model |
| `detection_confidence` | `0.5` | Initial detection threshold |
| `tracking_confidence` | `0.5` | Tracking threshold between frames |
