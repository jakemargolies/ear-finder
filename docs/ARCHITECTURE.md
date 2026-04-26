# System Architecture

## Overview

A real-time acoustic beamforming system that tracks a person's head in 3D space and steers a 4-channel speaker array to focus audio at their location.

Two operating modes are supported, selectable via `MODE` in `matlab/config.m`:

| Mode | Description | Prerequisites |
|---|---|---|
| `delay` | Local delay-and-sum, no GPU server | earfinder + netbridge + MATLAB |
| `avdar` | AV-DAR neural RIR + matched-filter FIR via GPU server | All of the above + SSH tunnel + AV-DAR server |

---

## Pipeline

```
┌──────────────────────────────────────────────────────────────────────┐
│                        LAPTOP (macOS, Apple Silicon)                 │
│                                                                      │
│  ┌─────────────────┐  [x,y,z]   ┌──────────────┐                   │
│  │   earfinder     │ ─────────► │  netbridge   │                   │
│  │   (Python)      │  internal  │  (Python)    │                   │
│  │                 │            │              │                   │
│  │  RealSense D455 │            └──────┬───────┘                   │
│  │  IR + depth     │                   │ UDP 127.0.0.1:5007        │
│  │  MediaPipe pose │                   │ 12 bytes: float32[x,y,z]  │
│  └─────────────────┘                   ▼                           │
│                              ┌──────────────────┐                  │
│                              │  beam_client.m   │                  │
│                              │  (MATLAB)        │                  │
│                              │                  │                  │
│  ┌── delay mode ─────────────┤  decodes pos     │                  │
│  │   compute delays locally  │  picks mode      ├──────────────┐   │
│  │   no server needed        │                  │              │   │
│  └───────────────────────────┤                  │   avdar mode │   │
│                              └────────┬─────────┘              │   │
│                                       │                        │   │
│                              audio chunks → audioPlayerRecorder│   │
│                                       │         MCHStreamer    │   │
│                                       ▼         I2S TosLink   │   │
│                              4-channel speaker array           │   │
└──────────────────────────────────────────────────────────────────┼──┘
                                                                   │
                              TCP JSON (via SSH tunnel or LAN)     │
                              {"type":"rx_pos","rx_pos":[x,y,z]}   │
                                                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        GPU SERVER  10.137.180.141  (Linux)           │
│                                                                      │
│              ┌───────────────────────────────────────┐              │
│              │  AV-DAR demo server  (Python, port 5005)│             │
│              │                                        │             │
│              │  1. Receive rx_pos from MATLAB          │             │
│              │  2. Run AV-DAR neural RIR inference     │             │
│              │     (4 speakers × 1 listener)           │             │
│              │  3. Compute matched-filter FIR bank     │             │
│              │                                        │             │
│              │  in:  {"rx_pos": [x, y, z]}            │             │
│              │  out: {"filters": [L×4], "fs": 16000}  │             │
│              └───────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Component Status

| Component | Language | Host | Status |
|---|---|---|---|
| `earfinder` | Python | Laptop | **Done** |
| `netbridge` | Python | Laptop | **To build** (see plan 02) |
| `matlab/beam_client.m` | MATLAB | Laptop | **Done** |
| `matlab/config.m` | MATLAB | Laptop | **Done** |
| `matlab/test_udp_rx.m` | MATLAB | Laptop | **Done** (test helper) |
| `scripts/inject_position.py` | Python | Laptop | **Done** (test helper) |
| AV-DAR demo server | Python | GPU server | **Done** (partner's code) |

---

## Data Flow

### earfinder → netbridge (in-process or loopback)
- **What:** `[x, y, z]` np.float32 meters, RealSense camera frame
- **How:** `netbridge` imports and calls `EarFinder` directly

### netbridge → MATLAB (UDP loopback)
- **What:** head position `[x, y, z]` in meters
- **Port:** `127.0.0.1:5007`
- **Format:** 12 bytes, little-endian float32[3]
- **Rate:** ~30 Hz when a person is detected; nothing sent on no-detection

### MATLAB → AV-DAR server (TCP JSON, `avdar` mode only)
- **What:** listener position request
- **Transport:** TCP, newline-delimited JSON (SSH tunnel or direct LAN)
- **Request:** `{"type":"rx_pos","sequence_id":N,"rx_pos":[x,y,z]}`
- **Response:** `{"type":"bf_filter","status":"ok","fs":16000,"shape":[L,4],"filters":[...],"elapsed_ms":T}`

### MATLAB → Speaker array
- **`delay` mode:** integer-sample delays + amplitude weights applied per chunk
- **`avdar` mode:** per-channel FIR convolution with `filter()`, state carried across chunks

---

## Coordinate System

All positions use the **RealSense camera frame**:
```
x = right
y = down
z = forward (into scene)
units = meters
origin = camera lens
```

Speaker positions in `matlab/config.m` and `config/room.toml` are measured in this frame.
The AV-DAR server's `SPEAKER_POSITIONS` must also use this frame.

### Known speaker geometry

4 speakers in an equally spaced horizontal line (~6 inches / 0.1524 m total),
mounted 8 cm above the camera at the same depth:

```
Speaker:   1        2        3        4
x (m):  -0.0762  -0.0254  +0.0254  +0.0762
y (m):  -0.08    -0.08    -0.08    -0.08
z (m):   0.00     0.00     0.00     0.00
```

---

## How to Run

### Delay mode (no server needed)

```bash
# Terminal 1 — laptop
python -m netbridge          # (once netbridge is built)

# Or for testing without earfinder:
python scripts/inject_position.py
```

```matlab
% MATLAB — ensure MODE = 'delay' in config.m
beam_client()
```

### AV-DAR mode

```bash
# GPU server — start AV-DAR demo server
python demo_server.py

# Laptop — open SSH tunnel
ssh -L 5005:127.0.0.1:5005 gpu-server

# Laptop — run netbridge
python -m netbridge
```

```matlab
% MATLAB — ensure MODE = 'avdar' in config.m
beam_client()
```

---

## Key Numbers

- Speed of sound: 343 m/s at ~20°C
- Speaker spacing: 2 inches (0.0508 m)
- Max inter-speaker delay: 0.0508 × 3 / 343 ≈ **0.44 ms**
- MCHStreamer sample rate: ~48 kHz → 1 sample ≈ 20 µs delay resolution
- AV-DAR server sample rate: 16 kHz (filters resampled to device rate in MATLAB)
