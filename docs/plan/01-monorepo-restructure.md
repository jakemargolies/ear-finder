# Plan 01: Monorepo Restructure

## Goal

Reorganize the repository from a single-module Python package into a monorepo
containing all four runtime components plus shared infrastructure.

## Proposed Directory Layout

```
ear-finder/                         ← repo root (rename optional)
│
├── earfinder/                      ← EXISTING Python package (no changes)
│   ├── __init__.py
│   ├── __main__.py
│   └── tracker.py
│
├── beamserver/                     ← NEW: GPU server Python package
│   ├── __init__.py
│   ├── __main__.py                 ← entry point: python -m beamserver
│   ├── room.py                     ← room geometry + speaker positions
│   └── weights.py                  ← beamforming weight computation
│
├── netbridge/                      ← NEW: thin Python process on the laptop
│   ├── __init__.py
│   └── __main__.py                 ← receives from earfinder, forwards to
│                                       beamserver, receives weights, relays
│                                       to MATLAB via UDP loopback
│
├── matlab/                         ← NEW: all MATLAB code
│   ├── spk_array_test.m            ← MOVE from repo root
│   ├── beam_client.m               ← NEW: receives weights, drives audio
│   └── config.m                    ← NEW: device name, channel count, etc.
│
├── config/                         ← NEW: shared runtime config
│   └── room.toml                   ← speaker positions, room dims, server addr
│
├── docs/
│   ├── ARCHITECTURE.md
│   └── plan/
│       ├── 01-monorepo-restructure.md  ← this file
│       ├── 02-transport-layer.md
│       ├── 03-beamserver.md
│       └── 04-matlab-client.md
│
├── pyproject.toml                  ← uv workspace root
├── .gitignore
└── README.md
```

## uv Workspace Setup

Convert to a uv workspace so `earfinder`, `beamserver`, and `netbridge` each
have their own `pyproject.toml` but share a single lockfile.

### Root `pyproject.toml` changes

```toml
[tool.uv.workspace]
members = ["earfinder", "beamserver", "netbridge"]
```

The root `pyproject.toml` becomes the workspace manifest. Move the current
content into `earfinder/pyproject.toml`.

### `beamserver/pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "beamserver"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "numpy",
    "tomllib; python_version < '3.11'",  # stdlib in 3.11+
]

[tool.hatch.build.targets.wheel]
packages = ["beamserver"]
```

### `netbridge/pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "netbridge"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "ear-finder",   # workspace dependency
    "numpy",
]

[tool.hatch.build.targets.wheel]
packages = ["netbridge"]
```

## Steps

1. Create `earfinder/pyproject.toml` by moving current root `pyproject.toml` content.
2. Rewrite root `pyproject.toml` as workspace manifest.
3. `mkdir beamserver netbridge matlab config docs/plan`
4. `git mv spk_array_test.m matlab/`
5. Create stub `__init__.py` and `__main__.py` in `beamserver/` and `netbridge/`.
6. Create `config/room.toml` with placeholder speaker positions.
7. Run `uv sync` to verify workspace resolves.
8. Update `.vscode/launch.json` with new module paths.

## Notes

- `beamserver` does not need pyrealsense2 or mediapipe — it runs on the GPU server.
- `netbridge` runs on the laptop and depends on `earfinder`.
- MATLAB code lives in `matlab/` and is not part of the Python build system.
- `config/room.toml` is the single source of truth for room geometry and is read
  by both `beamserver` (for speaker positions) and potentially `netbridge` (for
  server address).
