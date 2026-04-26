# Plan 04: MATLAB Client

## Status: Done

All MATLAB files are implemented and tested (UDP receive confirmed working).

## Files

| File | Role |
|---|---|
| `matlab/config.m` | All tunable constants — edit this before running |
| `matlab/beam_client.m` | Main entry point — run `beam_client()` in MATLAB |
| `matlab/test_udp_rx.m` | Standalone UDP position receive test |
| `matlab/spk_array_test.m` | Original one-shot delay-and-sum prototype (reference) |

---

## Operating Modes

Set `MODE` in `matlab/config.m` before running.

### `'delay'` — local delay-and-sum (default)

No GPU server needed. Computes per-channel delays from speaker geometry and
head position, applies integer-sample delays, plays audio.

**Only two processes required:** `inject_position.py` (or `netbridge`) + MATLAB.

### `'avdar'` — AV-DAR neural matched-filter FIR

MATLAB connects to the AV-DAR server via TCP, sends head position as JSON,
receives a full FIR filter bank (`[L, 4]`), and applies it per channel with
`filter()` carrying state across chunks.

**Prerequisites:** SSH tunnel active, AV-DAR server running, netbridge running.

---

## Configuration (`matlab/config.m`)

```matlab
MODE = 'delay';          % 'delay' or 'avdar'

% Speaker positions (camera frame: x=right, y=down, z=forward, meters)
SPEAKER_POSITIONS_M = [
   -0.0762, -0.08, 0.00;   % speaker 1 (leftmost)
   -0.0254, -0.08, 0.00;   % speaker 2
    0.0254, -0.08, 0.00;   % speaker 3
    0.0762, -0.08, 0.00;   % speaker 4 (rightmost)
];
SPEED_OF_SOUND  = 343.0;   % m/s

SERVER_HOST    = '10.137.180.141';   % GPU server IP
SERVER_PORT    = 5005;
SERVER_TIMEOUT = 5;                  % seconds
ALLOW_RESAMPLE = true;               % resample FIR from 16kHz to device fs

UDP_POS_PORT   = 5007;               % receives position from netbridge
DEVICE_NAME    = 'MCHStreamer I2S TosLink';
NUM_CHANNELS   = 4;
TONE_FREQ      = 1000;               % Hz
CHUNK_DURATION = 0.1;                % seconds per playback chunk
```

---

## Audio Architecture

**`delay` mode:** Each chunk builds a `[N, 4]` matrix by applying
integer-sample shifts and amplitude weights derived from speaker-to-head
distances. Weights are recomputed on every new position packet.

**`avdar` mode:** FIR filters from the server are applied with
`filter(b, 1, h, zi)` per channel. Filter state `zi` is preserved
across chunks for phase continuity. State resets when a new filter bank
arrives (brief transient is acceptable).

**Sample rate mismatch:** AV-DAR server outputs at 16 kHz. MCHStreamer
typically runs at 48 kHz. With `ALLOW_RESAMPLE = true`, each filter
column is resampled using `resample(b, p, q)` (polyphase, anti-aliased).

---

## How to Run

### Quick test (no earfinder, no netbridge)

```bash
# Terminal — inject fake sweeping positions
python scripts/inject_position.py
```

```matlab
% MATLAB — test UDP receive only
test_udp_rx          % prints decoded x/y/z as they arrive

% Or run the full audio client in delay mode
beam_client()
```

### Delay mode with live tracking

```bash
python -m netbridge   # (once built — wraps earfinder, sends UDP to port 5007)
```

```matlab
beam_client()
```

### AV-DAR mode

```bash
# 1. SSH tunnel
ssh -L 5005:127.0.0.1:5005 gpu-server

# 2. On GPU server — start AV-DAR server
python demo_server.py

# 3. Laptop
python -m netbridge
```

```matlab
% Set MODE = 'avdar' in config.m, then:
beam_client()
```

---

## Testing Individual Components

**Test UDP receive (verified working):**
```bash
python scripts/inject_position.py      # sends sweeping positions at 10 Hz
```
```matlab
test_udp_rx    % should print x/y/z matching the injector output
```

**Test server connection (no earfinder):**
```matlab
srv = tcpclient('127.0.0.1', 5005, 'Timeout', 10);
req = struct('type','rx_pos','sequence_id',int32(0),'rx_pos',[0.0 0.0 2.0]);
write(srv, uint8([jsonencode(req), newline]));
```

**Static position injection:**
```bash
python scripts/inject_position.py --static 0.0 0.0 2.0
```

---

## MATLAB Toolbox Requirements

| Toolbox | Used for |
|---|---|
| Audio Toolbox | `audioPlayerRecorder` |
| Signal Processing Toolbox | `resample` (avdar mode only) |
| Built-in (R2020b+) | `udpport`, `jsondecode`, `jsonencode` |
| Built-in (R2019b+) | `tcpclient` with `read`/`write` |
