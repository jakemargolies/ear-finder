# Plan 03: AV-DAR Server Integration

## Status

The GPU server component is **already written** by Ruizhe/marga. This document
describes how it works, how to configure it, and what still needs to be set up
before it can be used.

Server code: `demo_server.py` in the AV-DAR repo on the GPU machine at
`/home/marga/ruizhe/av-dar/`.

---

## What the Server Does

1. Listens on TCP port 5005 for newline-delimited JSON requests.
2. On each `rx_pos` request, runs AV-DAR neural network inference to predict
   room impulse responses (RIRs) from each of the 4 speakers to the listener.
3. Converts the 4 RIRs into a matched-filter FIR beamforming bank.
4. Returns the filter bank (`[L, 4]` float32) as JSON.

---

## Setup on the GPU Server

### 1. Fill in the placeholders in `demo_server.py`

The server has a clearly marked `PLACEHOLDER AREA` near the top. Set:

```python
CONFIG_DIR = "/home/marga/ruizhe/av-dar/.working/csip_EmptyRoom/CSIP-Empty-16K-20%/YYYY-MM-DD_HH-MM-SS"
# Replace YYYY-MM-DD_HH-MM-SS with the actual trained run folder name.

STATE_DICT_NAME = "weight_final.pt"
# Replace if the checkpoint has a different filename.
```

### 2. Set speaker positions in `demo_server.py`

Speaker positions must be in the **same coordinate frame as `rx_pos`** sent
from MATLAB (RealSense camera frame: x=right, y=down, z=forward, meters).

Known geometry — 4 speakers, equally spaced horizontal line, 8 cm above camera:

```python
SPEAKER_POSITIONS = np.array([
    [-0.0762, -0.08, 0.00],   # speaker 1 (leftmost)
    [-0.0254, -0.08, 0.00],   # speaker 2
    [ 0.0254, -0.08, 0.00],   # speaker 3
    [ 0.0762, -0.08, 0.00],   # speaker 4 (rightmost)
], dtype=np.float32)
```

Identity quaternions are fine for speakers facing forward:
```python
SPEAKER_QUATS_XYZW = np.array([
    [0.0, 0.0, 0.0, 1.0],  # speaker 1
    [0.0, 0.0, 0.0, 1.0],  # speaker 2
    [0.0, 0.0, 0.0, 1.0],  # speaker 3
    [0.0, 0.0, 0.0, 1.0],  # speaker 4
], dtype=np.float32)
```

### 3. Confirm network binding

The server binds to `HOST = "127.0.0.1"`. This means it only accepts
connections from localhost — SSH tunnel required from the laptop.

To accept direct LAN connections instead, change to `HOST = "0.0.0.0"`.

### 4. Run the server

```bash
cd /home/marga/ruizhe/av-dar
python demo_server.py
```

---

## Tuning Parameters

| Parameter | Default | Effect |
|---|---|---|
| `NUM_SAMPLE_DIRECTIONS` | 8192 | Path sampling density. Lower = faster inference, less accurate RIR. |
| `BF_FMIN` / `BF_FMAX` | 300 / 3000 Hz | Matched-filter frequency band. |
| `NORMALIZE_FILTERS` | `True` | Normalize FIR bank by peak value. |
| `CAUSALIZE_FILTERS` | `True` | Common circular shift to make filters causal. |
| `MAX_FILTER_LEN_TO_SEND` | `None` | Truncate FIR to reduce JSON payload size. Try `2048` for faster transfer. |

---

## Testing the Server Independently

From the laptop (with SSH tunnel active):

```python
import socket, json

s = socket.socket()
s.connect(("127.0.0.1", 5005))

req = json.dumps({"type": "rx_pos", "sequence_id": 0, "rx_pos": [0.0, 0.0, 2.0]}) + "\n"
s.sendall(req.encode())

buf = b""
while b"\n" not in buf:
    buf += s.recv(4096)

resp = json.loads(buf.split(b"\n")[0])
print(resp["shape"])        # e.g. [5120, 4]
print(resp["elapsed_ms"])   # inference time
```

Or from MATLAB directly:
```matlab
srv = tcpclient('127.0.0.1', 5005, 'Timeout', 30);
req = struct('type','rx_pos','sequence_id',int32(0),'rx_pos',[0.0 0.0 2.0]);
write(srv, uint8([jsonencode(req), newline]));
% wait, then check srv.NumBytesAvailable
```

---

## Coordinate Frame Note

The AV-DAR model was trained on a specific room mesh. The coordinate frame of
that mesh may differ from the RealSense camera frame. Confirm with Ruizhe that
the expected `rx_pos` units and axes match before running a real experiment.
If the frames differ, a static transform must be applied in `beam_client.m`
before sending `rx_pos` to the server.
