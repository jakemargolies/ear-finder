# Plan 02: Transport Layer

## Overview

```
earfinder (Python)
    │  [in-process]
    ▼
netbridge (Python, laptop)
    │
    │  UDP 127.0.0.1:5007
    │  12 bytes: little-endian float32[x, y, z]
    │  ~30 Hz when person detected
    ▼
beam_client.m (MATLAB, laptop)
    │
    │  [delay mode: compute locally, done]
    │
    │  [avdar mode: TCP JSON to GPU server]
    │  {"type":"rx_pos","sequence_id":N,"rx_pos":[x,y,z]}
    ▼
AV-DAR demo server (GPU server, port 5005)
    │
    │  TCP JSON response
    │  {"type":"bf_filter","fs":16000,"shape":[L,4],"filters":[...]}
    ▼
beam_client.m applies FIR filters → audioPlayerRecorder → speaker array
```

---

## Wire Format: netbridge → MATLAB

**Port:** `127.0.0.1:5007`
**Transport:** UDP
**Payload:** 12 bytes, little-endian

```
Offset  Type     Field
0       float32  x  (meters, right)
4       float32  y  (meters, down)
8       float32  z  (meters, forward)
```

Only sent when `earfinder` returns a non-None vector (person detected).
MATLAB decodes with `typecast(uint8(raw), 'single')`.

---

## Wire Format: MATLAB → AV-DAR server

**Transport:** TCP, newline-terminated JSON (`\n` = ASCII 10)
**Access:** Direct LAN (`10.137.180.141:5005`) or SSH tunnel (`127.0.0.1:5005`)

**Request:**
```json
{"type":"rx_pos","sequence_id":0,"rx_pos":[x,y,z]}
```

**Response:**
```json
{
  "type": "bf_filter",
  "status": "ok",
  "sequence_id": 0,
  "fs": 16000,
  "shape": [5120, 4],
  "filters": [[...L rows, 4 cols...]],
  "filter_order": "matlab_L_by_4",
  "elapsed_ms": 123.4
}
```

`filters` layout: `filters(:, ch)` is the FIR impulse response for speaker `ch`.
MATLAB applies it as `filter(filters(:,ch), 1, audio_chunk, zi{ch})`.

Response payloads can be large (~200 KB for a 5120-tap bank). `read_json_line`
in `beam_client.m` reads in chunks until it sees the newline terminator.

---

## Port Reference

| Port | Direction | Protocol | Content |
|---|---|---|---|
| `5005` | MATLAB → GPU server | TCP | JSON position request / FIR filter response |
| `5007` | netbridge → MATLAB | UDP loopback | 12-byte position vector |

---

## `netbridge` Implementation

`netbridge` is the thin laptop-side Python process that bridges `earfinder`
to MATLAB. It is **not yet built**; the sketch below is what needs to be written.

```python
# netbridge/__main__.py
import socket
import struct
import tomllib
from earfinder import EarFinder

with open("config/room.toml", "rb") as f:
    cfg = tomllib.load(f)

MATLAB_ADDR = ("127.0.0.1", cfg["network"]["port_matlab"])
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

with EarFinder() as ef:
    for vec in ef.stream():
        if vec is None:
            continue
        sock.sendto(struct.pack("<3f", *vec), MATLAB_ADDR)
```

That's the whole thing. `netbridge` does not talk to the GPU server directly —
MATLAB handles that connection.

---

## SSH Tunnel (avdar mode only)

The AV-DAR server binds to `127.0.0.1:5005` on the GPU machine, so an SSH
tunnel is required unless the laptop is on the same LAN segment:

```bash
ssh -L 5005:127.0.0.1:5005 gpu-server
```

MATLAB then connects to `127.0.0.1:5005` as configured in `matlab/config.m`.
If on the same LAN, point `SERVER_HOST` directly at `10.137.180.141`.

---

## Latency Budget

| Segment | Expected |
|---|---|
| earfinder frame capture + MediaPipe | ~40–50 ms (30 Hz camera) |
| netbridge → MATLAB UDP loopback | < 1 ms |
| MATLAB → AV-DAR server (LAN) | 1–5 ms |
| AV-DAR inference (GPU) | ~100–500 ms (model dependent) |
| Server → MATLAB response | 1–5 ms |
| **Total (avdar mode)** | **~150–560 ms** |
| **Total (delay mode)** | **~40–50 ms** |

AV-DAR inference dominates latency. For slow head movements this is acceptable;
for fast tracking the delay mode is more responsive.
