# AGENTS.md — FOBOS Positioner UI

This file describes the architecture, conventions, and current state of the
FOBOS positioner GUI for the benefit of any AI agent or new contributor working
on this codebase.

---

## What this project is

A graphical control interface built in **PySide6** for operating robotic fibre
positioners for the FOBOS instrument. Each positioner consists of two arms
joined at a pivot, each with full 360-degree rotation. The total reachable area
is an annulus, and all motion is constrained within it.

The UI gives an operator three ways to command a positioner:

- Numeric α/β angle input with a go-to button
- Click-to-move on a live camera view (with an annulus overlay projected onto it)
- Scripted move sequences (future version, planned but not yet implemented)

---

## Project structure

```
fobos_ui/
├── main.py                   # Entry point. Creates QApplication and MainWindow.
├── app_model.py              # Central state store. Single source of truth.
├── constants.py              # Shared string constants (positioner states).
├── main_window.py            # Assembles widgets, wires all signals/slots.
├── workers/
│   ├── fps_manager.py         # QThread. Initializes FPS, polls positioners at 3Hz.
│   ├── positioner_worker.py  # QObject. Owns positioner commands.
│   └── vimba_worker.py       # QThread. Owns vmbpy camera session and streaming.
└── widgets/
    ├── camera_widget.py      # Frame display, annulus overlay, click-to-move.
    ├── control_panel.py      # α/β inputs and go-to button.
    └── status_bar.py         # Position readout and move state display.
```

---

## Architecture

The project follows an MVC-inspired pattern with strict separation between
state, hardware, and display. The three rules that must not be broken:

1. **Nothing blocking runs on the main thread.** All hardware calls live in
   worker threads.
2. **Workers and widgets never talk directly.** All cross-thread communication
   goes through Qt signals and slots.
3. **`AppModel` is the single source of truth.** No widget stores its own copy
   of position or state — it reads from the model.

### Threading model

There are three threads:

- **Main thread** — Qt event loop. Runs all widgets. Never blocks.
- **`FPSManager` thread** — Initializes the `FPS` instance once on startup over
  the CAN@net connection and emits `ready(fps)`. It runs its own `asyncio` event
  loop. After initialization, it continuously polls all positioners at 3 Hz and
  emits `positions_updated(dict)`.
- **`PositionerWorker` object(s)** — One per positioner ID. These are `QObject`s
  (not threads). They receive the `FPS` object, its `asyncio` event loop, and a
  positioner ID. They accept move commands via slots and submit motion commands
  directly to the `FPSManager` event loop using `asyncio.run_coroutine_threadsafe`.
- **`VimbaWorker` thread** — Owns the vmbpy camera session for the lifetime of
  the app. Streams frames and emits `frame_ready(np.ndarray)` on each complete
  frame.

### Signal/slot map

This is the pub/sub backbone of the app. Think of signals as ROS2 topics —
emitters don't know who's listening, receivers don't know who's emitting.

| Signal | Emitted by | Connected to |
|---|---|---|
| `ready(fps)` | `FPSManager` | `MainWindow.on_fps_ready` |
| `positions_updated(dict)` | `FPSManager` | `AppModel.update_positions` |
| `move_started(int)` | `PositionerWorker` | `AppModel.update_positioner_state` |
| `move_done(int)` | `PositionerWorker` | `AppModel.update_positioner_state` |
| `error(int, str)` | `PositionerWorker` | `AppModel.update_positioner_state` |
| `frame_ready(np.ndarray)` | `VimbaWorker` | `CameraWidget.update_frame` |
| `model_updated()` | `AppModel` | All widgets that display state |
| `move_requested(α, β)` | `ControlPanel` / `CameraWidget` | `PositionerWorker.request_move` |

All connections are made in `main_window.py`. That is the only file that needs
to know about both workers and widgets simultaneously.

---

## Key dependencies

| Package | Purpose |
|---|---|
| `PySide6` | GUI framework |
| `jaeger-core` | Positioner control API (async, CAN@net over TCP/IP) |
| `vmbpy` | Allied Vision camera SDK (Linux/macOS only — see below) |
| `numpy` | Frame data handling |

### jaeger-core

Installed directly from GitHub:

```
jaeger-core @ git+https://github.com/kbwestfall/jaeger-core.git
```

All jaeger-core calls are `async`. The `FPSManager` runs an
`asyncio` event loop via `asyncio.new_event_loop()` inside `QThread.run()`.
Move commands submitted from the main thread to a `PositionerWorker` use
`asyncio.run_coroutine_threadsafe()` to safely cross the thread boundary
and execute on the `FPSManager`'s event loop.

The `FPS` object must be initialized **exactly once** and its internal tasks
remain bound to the event loop that initialized it. This is handled by `FPSManager`
which now owns the `FPS` instance for the lifetime of the application.

Configuration lives in `~/.jaeger.yaml` (CAN@net IP and bus settings).

### vmbpy

`vmbpy` does not have a macOS wheel on PyPI. Use the platform-neutral `any`
wheel from Allied Vision's GitHub releases, which loads native Vimba X SDK
libraries at runtime. Vimba X must be installed on the system separately.

In `pyproject.toml`, pin vmbpy to the `any` wheel:

```toml
"vmbpy @ https://github.com/alliedvision/VmbPy/releases/download/1.2.1/vmbpy-1.2.1-py3-none-any.whl"
```

Frame handler pattern — always `.copy()` the frame buffer and always re-queue:

```python
def frame_handler(self, cam, stream, frame):
    if frame.get_status() == vmbpy.FrameStatus.Complete:
        self.frame_ready.emit(frame.as_numpy_ndarray().copy())
    cam.queue_frame(frame)
```

---

## State management

`AppModel` (inherits `QObject`) holds:

- `positioners: dict` — A dictionary of positioner states keyed by ID. Each entry is a dict:
  - `alpha: float` — current α position in degrees
  - `beta: float` — current β position in degrees
  - `state: str` — one of the constants below

`AppModel` emits `model_updated()` on any state change. Widgets connect to this
signal and read from the model directly — they do not receive state as signal
arguments.

### Positioner state constants (`constants.py`)

```python
POSITIONER_READY   = "ready"
POSITIONER_MOVING  = "moving"
POSITIONER_ERROR   = "error"
```

---

## Asyncio / QThread bridge

This is the trickiest part of the architecture. The pattern used throughout:

```python
class PositionerWorker(QObject):
    def __init__(self, fps, loop, positioner_id):
        super().__init__()
        self._fps = fps
        self._loop = loop

    @Slot(float, float)
    def request_move(self, alpha, beta):
        # called from main thread via signal/slot
        # submit coroutine to the worker's loop safely
        asyncio.run_coroutine_threadsafe(
            self._do_move(alpha, beta), self._loop
        )
```

Never `await` directly from a slot. Never call asyncio primitives from the
wrong thread. Use `run_coroutine_threadsafe` for main → worker and
`call_soon_threadsafe` for any other cross-thread asyncio calls (e.g. setting
stop events on shutdown).

---

## Shutdown

`MainWindow` must call `worker.stop()` on all workers (or poller threads) before closing.
`FPSManager.stop()` sets the asyncio stop event (via
`call_soon_threadsafe`) and calls `self.wait()` to block until the thread exits
cleanly. Without this, the asyncio loop may still be running when Python tears
down and produce noisy errors.

---

## What is not yet implemented

- `VimbaWorker` — stub exists, real vmbpy integration pending
- `CameraWidget` — frame rendering and annulus overlay pending
- Click-to-move coordinate transform (pixel → α/β) — geometry not yet defined
- `ScriptPanel` — planned for future version, collision checking required

---

## Development notes

- Use `uv` for dependency management (`uv sync`, `uv run`)
- The deployment target is Linux; development on macOS is supported with the
  vmbpy `any` wheel and Vimba X installed
- Hardware config (`~/.jaeger.yaml`) must exist before running against real
  hardware; a mock/stub mode should be implemented for UI development without
  hardware access
- Positioner ID is currently hardcoded — should be made configurable