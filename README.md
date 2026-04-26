# ear-finder

Real-time acoustic beamforming system. Tracks a person's head in 3D using an Intel RealSense D455 and steers a 4-channel speaker array to focus audio at their location.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system diagram.

---

## Components

| Component | Location | Description |
|---|---|---|
| `earfinder` | `earfinder/` | Python library — locates head in 3D from RealSense IR + depth |
| `netbridge` | `netbridge/` | Python process — relays position from earfinder to MATLAB via UDP |
| `beam_client` | `matlab/beam_client.m` | MATLAB — receives position, computes beamforming, drives speaker array |
| AV-DAR server | GPU server | Partner's code — neural RIR inference + matched-filter FIR (avdar mode only) |

---

## Quick Start

### Delay mode (no GPU server needed)

Two processes: `netbridge` on the laptop, `beam_client` in MATLAB.

```bash
python -m netbridge
```

```matlab
% ensure MODE = 'delay' in matlab/config.m
beam_client()
```

### AV-DAR mode (GPU server)

```bash
# 1. SSH tunnel to GPU server
ssh -L 5005:127.0.0.1:5005 gpu-server

# 2. On GPU server — start AV-DAR demo server
python demo_server.py

# 3. Laptop
python -m netbridge
```

```matlab
% ensure MODE = 'avdar' in matlab/config.m
beam_client()
```

### Testing without a camera

Inject fake position packets from the terminal to test netbridge or beam_client independently:

```bash
python scripts/inject_position.py          # sweeping positions at 10 Hz
python scripts/inject_position.py --static 0.0 0.0 2.0   # fixed position
```

To verify MATLAB receives them correctly:
```matlab
test_udp_rx    % prints decoded x/y/z as packets arrive
```

---

## MATLAB Configuration

All tunable constants are in `matlab/config.m`. The most important ones:

```matlab
MODE = 'delay';   % 'delay' (local) or 'avdar' (GPU server)

SPEAKER_POSITIONS_M = [
   -0.075, -0.08, 0.00;   % speaker 1 (leftmost)
   -0.025, -0.08, 0.00;   % speaker 2
    0.025, -0.08, 0.00;   % speaker 3
    0.075, -0.08, 0.00;   % speaker 4 (rightmost)
];
% x = right, y = down, z = forward from camera, meters
% 4-speaker array, 5 cm center-to-center, 8 cm above camera, same depth
```

---

## earfinder

Locates a person's head in 3D space using an Intel RealSense D455 and MediaPipe Pose. Returns the XYZ displacement from the camera to the midpoint between the subject's ears.

```
x = right  |  y = down  |  z = forward  |  units = meters
```

### macOS / Apple Silicon notes

- **Color camera is inaccessible via libusb.** macOS's UVC kernel driver claims the D455 color camera exclusively. This module uses the **left infrared (IR) stream** instead.
- **pyrealsense2 is not pip-installable on macOS arm64** and must be built from source with `-DFORCE_RSUSB_BACKEND=ON`.
- **USB 3.0 cable required.** USB-C cables can be limited to USB 2.0 speeds, which prevents the depth stream from working.
- **No sudo required.** The IR and depth streams are not UVC devices.
- **mediapipe ≥ 0.10 drops the legacy `solutions` API** on macOS arm64. This module uses the Tasks API with a downloaded model file.

### Requirements

- Apple Silicon Mac (M1/M2/M3 or later)
- macOS Ventura or later
- Intel RealSense D455
- USB-C cable rated USB 3.1 Gen 1 or better
- Python 3.11 (via `uv`)
- Homebrew

### Installation

#### 1. Install system dependencies

```bash
brew install librealsense cmake uv
```

#### 2. Clone and set up the project

```bash
git clone <repo-url>
cd ear-finder
uv sync --extra dev
```

#### 3. Build pyrealsense2 from source

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

#### 4. Download the MediaPipe pose model

```bash
cd /path/to/ear-finder
curl -L -o pose_landmarker.task \
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
```

### Verify the camera

```bash
sudo /opt/homebrew/bin/rs-enumerate-devices
```

You should see `Usb Type Descriptor: 3.x`. If it shows `2.1`, the cable is USB 2.0 — replace it.

### Running earfinder standalone

```bash
python -m earfinder           # console output
python -m earfinder --visual  # annotated IR video window
```

```
ear-finder: streaming head position (x, y, z) in meters. Ctrl-C to stop.

  x=+0.042  y=+0.115  z=+1.203 m
```

### Visual mode indicators

| Indicator | Meaning |
|---|---|
| Cyan dots | Left and right ear landmarks |
| Cyan line | Connection between ears |
| Green circle + crosshair | Head midpoint — the reported 3D position |
| Green text | `x / y / z` in meters |
| Orange text | Pose detected but depth unavailable at midpoint |
| Red text | No person detected |

### Python API

```python
from earfinder import EarFinder

with EarFinder() as ef:
    for vec in ef.stream():
        if vec is not None:
            print(vec)  # np.ndarray [x, y, z] in meters
```

| Parameter | Default | Description |
|---|---|---|
| `serial` | `None` | RealSense device serial number |
| `width` | `848` | Stream width in pixels |
| `height` | `480` | Stream height in pixels |
| `fps` | `30` | Frame rate |
| `model_path` | `pose_landmarker.task` | Path to MediaPipe pose landmarker model |
| `detection_confidence` | `0.5` | Initial detection threshold |
| `tracking_confidence` | `0.5` | Tracking threshold between frames |
