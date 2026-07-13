# AGENTS.md — FOBOS Positioner UI

This file describes the architecture, conventions, and current state of the
FOBOS positioner GUI for the benefit of any AI agent or new contributor working
on this codebase. This article should be updated when there are any changes or updates to the codebase.


---

## What this project is

A graphical control interface built in **PySide6** for operating robotic fibre
positioners for the FOBOS instrument. Each positioner consists of two arms
joined at a pivot, each with full 360-degree rotation. The total reachable area
is an annulus, and all motion is constrained within it.

The UI gives an operator 2 ways to command a positioner:

- Numeric α/β angle input with a go-to button (manual single-positioner move), highly similar to the CLI tool
- Click-to-queue on the 2D grid view or the live camera view; a single "Send
  Targets" button dispatches all queued moves in one batch `goto()` call

---

## Project structure

```
fobos-gui/                        # repo root
├── main.py                       # Entry point. Creates QApplication, loads MainWindow.
├── app_model.py                  # Central state store. Single source of truth.
├── main_window.py                # Assembles widgets, wires all signals/slots, owns move dispatch.
├── style.qss                     # QSS dark-theme stylesheet loaded at startup.
├── calibration.json              # Persisted camera↔physical calibration (auto-read/written).
├── pyproject.toml                # uv-managed dependencies.
├── helpers/
│   ├── constants.py              # PositionerState enum, arm lengths, normalize_for_positioner().
│   ├── annulus.py                # solve_inverse_kinematics(x, y, l1, l2) → two solutions.
│   ├── geometry.py               # get_clicked_positioner() — click hit-detection.
│   ├── drawing.py                # draw_positioner(), draw_coordinate_grid() — shared QPainter routines.
│   ├── projection.py             # PositionerProjection — projective transform (physical↔camera).
│   ├── calibration_io.py         # save_calibration(), load_calibration(), is_valid_calibration_quad().
│   ├── circle_center.py          # Standalone calibration utility (not imported by main app).
│   └── 4pt_tf.py                 # Legacy prototype (not imported by main app).
├── workers/
│   ├── fps_manager.py            # QThread. Owns FPS init, asyncio loop, 5 Hz poll.
│   ├── positioner_worker.py      # QObject. CURRENTLY UNUSED — kept for reference (see note).
│   ├── mock_fps.py               # MockFPS / MockPositioner — enabled via FOBOS_MOCK=1.
│   ├── stream_worker.py          # QThread. Streams from RPi5 camera bridge via WebSockets.
│   └── vimba_worker.py           # QThread. Owns vmbpy camera session and streaming.
└── widgets/
    ├── camera_widget.py          # Live frame display, projected positioner overlay, click-to-queue.
    ├── grid2d.py                 # 2D top-down positioner view, click-to-queue.
    ├── control_panel.py          # α/β inputs, go-to button, batch send, solution swap, calibrate.
    ├── status_bar.py             # Position readout, connection status, reconnect buttons.
    ├── pan_zoom_mixin.py         # Shared pan/zoom logic for Grid2d and CameraWidget.
    └── view2D.py                 # LEGACY — single-positioner precursor to Grid2d; not wired into MainWindow.
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

- **Main thread** — Qt event loop. Runs all widgets and `AppModel`. Never blocks.
- **`FPSManager` thread** — Initializes the `FPS` instance on startup, runs a
  `asyncio` event loop via `asyncio.new_event_loop()`, polls all positioners at
  **5 Hz** (`POLL_INTERVAL = 1/5`), and emits `ready(fps, loop)` and
  `positions_updated(dict)`. The asyncio loop runs with `loop.run_forever()` and
  is stopped by jaeger-core's `fps.shutdown()` (which calls `loop.stop()`
  internally).
- **`VimbaWorker` / `StreamWorker` thread** — Owns the camera session or WebSocket stream for the lifetime of
  the app. Streams frames with a synchronous polling loop (`cam.get_frame()`) or an async WebSocket loop
  and emits `frame_ready(np.ndarray)` on each complete frame.


> **Note on `PositionerWorker`:** `workers/positioner_worker.py` exists but
> is **not currently used** — move dispatch was refactored into
> `MainWindow._do_batch_move` (see Move Dispatch below). The file is kept in
> place as a reference for the single-positioner async dispatch pattern;
> do not wire it up or add new features to it.

### Move dispatch

All positioner motion goes through `MainWindow._do_batch_move`, an `async`
coroutine that runs on the `FPSManager`'s asyncio loop:

```python
asyncio.run_coroutine_threadsafe(
    self._do_batch_move(targets), self._fps_loop
)
```

`targets` is a `{pid: (alpha_deg, beta_deg)}` dict. Angle normalization to
`[-10°, 370°]` via `normalize_for_positioner()` happens here — widgets emit
raw IK output. Results signal back to the main thread via private queued
signals:

```python
class MainWindow(QMainWindow):
    _move_batch_succeeded = Signal(list)  # [pid, ...] — runs on FPSManager thread; auto-queued
    _move_batch_failed    = Signal(list)  # [pid, ...] — same
```

Because these signals are class-level `Signal` declarations on a `QObject`,
PySide6 auto-promotes them to `QueuedConnection` when emitted from a non-main
thread, ensuring `AppModel` is only mutated from the Qt event loop.

The two entry points:
- **Single manual move**: `MainWindow.on_move_requested(pid, alpha, beta)` —
  triggered by `ControlPanel.move_requested`.
- **Batch queued move**: `MainWindow.on_batch_move_requested()` — reads
  `AppModel.get_queued_moves()` and dispatches them all in one `goto()` call,
  triggered by `ControlPanel.batch_move_requested`.

### Signal/slot map

All connections are made in `main_window.py`. That is the only file that needs
to know about both workers and widgets simultaneously.

| Signal | Emitted by | Connected to |
|---|---|---|
| `ready(fps, loop)` | `FPSManager` | `MainWindow.on_fps_ready` |
| `positions_updated(dict)` | `FPSManager` | `AppModel.update_positions` |
| `error(str)` | `FPSManager` | `MainWindow.on_fps_error` |
| `connection_status(bool)` | `FPSManager` | `AppModel.set_fps_connected` |
| `frame_ready(np.ndarray)` | `VimbaWorker` / `StreamWorker` | `CameraWidget.update_frame` (QueuedConnection) |
| `error(str)` | `VimbaWorker` / `StreamWorker` | `MainWindow.on_vimba_error` |
| `connection_status(bool)` | `VimbaWorker` / `StreamWorker` | `AppModel.set_camera_connected` |
| `model_updated()` | `AppModel` | `MainWindow._on_model_updated` → all widgets |
| `connection_updated()` | `AppModel` | `MainWindow._on_connection_updated` → `StatusBar.update_connections` |
| `move_requested(pid, α, β)` | `ControlPanel` | `MainWindow.on_move_requested` |
| `batch_move_requested()` | `ControlPanel` | `MainWindow.on_batch_move_requested` |
| `move_queued(pid, solutions)` | `Grid2d` / `CameraWidget` | `AppModel.queue_move` |
| `selection_changed(pid)` | `ControlPanel` / `Grid2d` / `CameraWidget` | `AppModel.set_selected_positioner` |
| `swap_solution_requested(pid)` | `ControlPanel` | `AppModel.swap_solution` |
| `calibrate_requested()` | `ControlPanel` | `CameraWidget.start_calibration` |
| `calibration_completed()` | `CameraWidget` | `ControlPanel.on_calibration_completed` |
| `swap_requested()` | `Grid2d` / `CameraWidget` | `MainWindow.on_swap_views_requested` |
| `reconnect_fps_requested()` | `StatusBar` | `MainWindow.reconnect_fps` |
| `reconnect_camera_requested()` | `StatusBar` | `MainWindow.reconnect_camera` |
| `exposure_changed(int)` | `CameraWidget` | `VimbaWorker.set_exposure` / `StreamWorker.set_exposure` |
| `gain_changed(float)` | `CameraWidget` | `VimbaWorker.set_gain` / `StreamWorker.set_gain` |
| `laser_status_received(dict)` | `StreamWorker` | (Future laser UI) |
| `_move_batch_succeeded(list)` | `MainWindow` (asyncio thread) | `MainWindow._on_batch_move_success` |
| `_move_batch_failed(list)` | `MainWindow` (asyncio thread) | `MainWindow._on_batch_move_failure` |

---

## Key dependencies

| Package | Purpose |
|---|---|
| `PySide6` | GUI framework |
| `jaeger-core` | Positioner control API (async, CAN@net over TCP/IP) |
| `vmbpy` | Allied Vision camera SDK (Linux/macOS only — see below) |
| `numpy` | Frame data handling |
| `scikit-image` | `ProjectiveTransform` in `helpers/projection.py` |
| `opencv-python` | `frame.as_opencv_image()` in `VimbaWorker`, `cv2.imdecode` in `StreamWorker` |
| `websockets` | WebSocket client for `StreamWorker` |


### jaeger-core

Installed directly from GitHub (kbwestfall fork):

```
jaeger-core @ git+https://github.com/kbwestfall/jaeger-core.git
```

All jaeger-core calls are `async`. The `FPSManager` runs an asyncio event
loop via `asyncio.new_event_loop()` inside `QThread.run()`. Move commands
submitted from the main thread use `asyncio.run_coroutine_threadsafe()` to
safely cross the thread boundary and execute on the `FPSManager`'s event loop.

The `FPS` object must be initialized **exactly once** and its internal tasks
remain bound to the event loop that initialized it. `FPSManager` owns the
`FPS` instance for the lifetime of the application. On reconnect,
`MainWindow.reconnect_fps()` calls `poller.stop()` (which shuts down the FPS
singleton via `fps.shutdown()`), then constructs a fresh `FPSManager`.

Configuration lives in `~/.jaeger.yaml` (CAN@net IP and bus settings).

#### FPS singleton teardown on failed init

If `FPS()` raises "already running" (stale singleton from a previous failed
attempt), `FPSManager._main()` retrieves the stale instance and shuts it down
before constructing a fresh one:

```python
try:
    self._fps = FPS()
except Exception:
    stale = FPS.get_instance()
    if stale is not None:
        await stale.shutdown()
    self._fps = FPS()
```

#### Connection drops and timeouts

The underlying CAN network connection can drop, causing `asyncio`/CAN socket
to print `socket.send() raised exception.` to stdout.

When this happens:
- `jaeger-core` has no auto-reconnect; subsequent `update_position()` calls
  silently return cached values after a multi-second timeout.
- `FPSManager` measures how long `update_position()` takes. If it exceeds
  1.5 s on 3 consecutive cycles, `connection_status(False)` is emitted.
- The operator uses the "Reconnect FPS" button in `StatusBar` to trigger
  `MainWindow.reconnect_fps()`, which tears down and rebuilds the worker.

#### Mock mode

Set `FOBOS_MOCK=1` in the environment to run without hardware. `FPSManager`
will instantiate `MockFPS` from `workers/mock_fps.py` instead of the real
`FPS`. `MockFPS` exposes `initialise()`, `update_position()`, `goto()`,
and `shutdown()` and simulates 1-second travel time on `goto()`.

### vmbpy

`vmbpy` does not have a macOS wheel on PyPI. A local copy of the platform-
neutral `any` wheel is vendored in the repo root. In `pyproject.toml`:

```toml
[tool.uv.sources]
vmbpy = { path = "vmbpy-1.0.4-py3-none-any.whl" }
```

Vimba X SDK must be installed separately on the system.

`VimbaWorker` uses a **synchronous polling** pattern (not the callback API):

```python
with VmbSystem.get_instance() as vmb:
    with cameras[0] as cam:
        cam.set_pixel_format(PixelFormat.Bgr8)
        while self._running and not self.isInterruptionRequested():
            frame = cam.get_frame()
            image = frame.as_opencv_image().copy()
            self.frame_ready.emit(image)
```

If `vmbpy` fails to import (e.g. Vimba X not installed), `VimbaWorker`
emits `error(str)` and `connection_status(False)` and returns immediately.
The UI continues to function without camera support.

### StreamWorker (RPi5 Camera Bridge)

When `FOBOS_CAMERA=stream` is set in the environment, the app uses `StreamWorker` instead of `VimbaWorker`. This connects via WebSockets to an RPi5 camera bridge running on `FOBOS_STREAM_HOST` (default `raspberrypi.local`) on port `FOBOS_STREAM_PORT` (default `8765`).

It connects to two endpoints:
- `/video`: Receives JPEG frames which are decoded to OpenCV images and emitted via `frame_ready`.
- `/control`: A bidirectional channel for sending camera settings (exposure, gain) and laser control commands (`laser_on`, `laser_off`, `set_laser_intensity`, `request_status`), and receiving `laser_status_received`.

Signal names and types are intentionally identical to `VimbaWorker` so they can be swapped without wiring changes.

---

## State management

`AppModel` (inherits `QObject`) holds:

- `positioners: dict` — keyed by positioner ID. Each entry:
  - `alpha: float` — current α position in degrees
  - `beta: float` — current β position in degrees
  - `state: str` — one of the `PositionerState` values below
  - `center: tuple` — physical (x, y) location in positioner coordinate space (mm)
  - `queued_target: tuple | None` — `(alpha, beta)` of the currently queued IK target
  - `queued_solutions: list` — both IK solutions returned by `solve_inverse_kinematics`
  - `queued_solution_index: int` — index of the active solution (0 or 1)
- `selected_positioner_id: int | None`
- `fps_connected: bool`
- `camera_connected: bool`

`AppModel` emits `model_updated()` on any positioner state change, and
`connection_updated()` when connection flags change. Widgets connect to these
signals and read from the model directly — they do not receive state as signal
arguments.

### Positioner state constants (`helpers/constants.py`)

```python
class PositionerState(StrEnum):
    READY  = "ready"
    MOVING = "moving"
    ERROR  = "error"
```

`StrEnum` means `PositionerState.READY == "ready"` is `True`, so existing
string comparisons in widgets remain valid.

---

## Camera to physical calibration

Before click-to-move works in the camera view, the operator must calibrate the
projective transform between camera pixel space and physical positioner space
(units: mm from the fibre plane center).

**Workflow (triggered by ControlPanel "Calibrate" button):**

1. `ControlPanel.calibrate_requested` → `CameraWidget.start_calibration()`
2. An unclosable `QDialog` instructs the operator to click four corners of a
   known physical rectangle in order: TL → TR → BL → BR. The physical corner
   coordinates are hardcoded in `CameraWidget.physical_pts`.
3. After 4 clicks, `is_valid_calibration_quad()` validates the quad (shoelace
   area > 10,000 px²).
4. `PositionerProjection.calibrate(physical_pts, camera_pts)` fits a
   `skimage.transform.ProjectiveTransform`.
5. `save_calibration()` writes `calibration.json` to the repo root.
6. On next launch, `CameraWidget.__init__` calls `load_calibration()` and
   restores the transform automatically.

`PositionerProjection` exposes:
- `physical_to_camera(x, y)` — forward transform
- `camera_to_physical(x, y)` — inverse transform
- `get_qtransform()` — returns a `QTransform` for use directly with `QPainter`
  to render positioner overlays in camera space.

---

## Click-to-queue / batch move workflow

Both `Grid2d` and `CameraWidget` implement the same click-to-queue pattern:

1. **Click inside a positioner's reachable annulus**: `get_clicked_positioner()`
   identifies the target positioner (prioritises the currently selected one).
2. **If a different positioner is clicked**: `selection_changed` is emitted —
   no move is queued on the first click.
3. **If the already-selected positioner is clicked**: relative offset from that
   positioner's `center` is computed, then `solve_inverse_kinematics` produces
   up to two `(alpha, beta)` solutions.
4. `move_queued(pid, solutions)` is emitted → `AppModel.queue_move()` stores
   both solutions and marks `queued_target` to the first one.
5. A **dashed blue arm overlay** is drawn showing the queued target.
6. The operator can click **"Swap Solution"** in `ControlPanel` to toggle
   between the two IK solutions (`AppModel.swap_solution()`).
7. **"Send N Targets"** in `ControlPanel` emits `batch_move_requested` →
   `MainWindow.on_batch_move_requested()` → `asyncio.run_coroutine_threadsafe(
   _do_batch_move(targets), fps_loop)`.
8. On completion, `_move_batch_succeeded` or `_move_batch_failed` signals
   update positioner state back on the main thread.

The **kinematic frame convention** applied in both views:

```python
# The positioner's local X/Y are inverted relative to the global axes
solutions = solve_inverse_kinematics(-rel_x, -rel_y, SHORT_ARM_LENGTH, LONG_ARM_LENGTH)
```

And in `drawing.py`:

```python
painter.scale(-1, -1)  # flip painter into positioner's kinematic frame
```

---

## Asyncio / QThread bridge

This is the trickiest part of the architecture. The pattern used by
`MainWindow` for move dispatch:

```python
# Called from main thread (button click / slot)
asyncio.run_coroutine_threadsafe(
    self._do_batch_move(targets), self._fps_loop
)

# _do_batch_move runs on FPSManager's asyncio loop thread
async def _do_batch_move(self, targets: dict):
    normalized = {
        pid: (normalize_for_positioner(a), normalize_for_positioner(b))
        for pid, (a, b) in targets.items()
    }
    try:
        await self._fps.goto(normalized)
        self._move_batch_succeeded.emit(list(normalized.keys()))
    except Exception as e:
        self._move_batch_failed.emit(list(normalized.keys()))
```
This is essentially due to jaeger-core being written in an async style. Because of this, we run jaeger-core commands on its own thread, preventing the GUI from being blocked.

Never `await` directly from a slot. Never call asyncio primitives from the
wrong thread. Use `run_coroutine_threadsafe` for main → asyncio-loop and
`call_soon_threadsafe` for any other cross-thread asyncio calls (e.g. setting
stop events on shutdown):

```python
def stop(self):
    if self._loop and not self._loop.is_closed():
        if self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._fps and hasattr(self._fps, "shutdown"):
            asyncio.run_coroutine_threadsafe(self._fps.shutdown(), self._loop)
        else:
            self._loop.call_soon_threadsafe(self._loop.stop)
    self.wait()
```

---

## Layout and view swapping

`MainWindow` lays out two `QSplitter`s:

```
main_splitter (Horizontal)
├── current_main_view   (initially Grid2d)
└── right_splitter (Vertical)
    ├── StatusBar
    ├── current_small_view  (initially CameraWidget)
    └── ControlPanel
```

The "Swap Views" button (on both `Grid2d` and `CameraWidget`) calls
`MainWindow.on_swap_views_requested()`, which uses `QSplitter.replaceWidget()`
to atomically exchange the two views. Each view exposes a `swap_button`
attribute that is shown only when the widget is in the small (right-panel)
position.

---

## Shutdown

`MainWindow.closeEvent` calls `worker.stop()` on all workers before the
event loop exits:

```python
def closeEvent(self, event):
    if self.vimba_worker:
        self.vimba_worker.stop()
    if self.poller:
        self.poller.stop()
    super().closeEvent(event)
```

`FPSManager.stop()` sets the asyncio stop event via `call_soon_threadsafe`,
then submits `fps.shutdown()` (which calls `loop.stop()` internally), then
calls `self.wait()` to block until the thread exits cleanly.

`VimbaWorker.stop()` sets `self._running = False`, calls
`requestInterruption()`, and waits.

---

## Development notes

- Use `uv` for dependency management (`uv sync`, `uv run`)
- Run without hardware: `FOBOS_MOCK=1 uv run main.py`
- Run with camera stream from RPI, use `FOBOS_CAMERA=stream uv run main.py`
- When using the stream backend, also set:
  - `FOBOS_STREAM_HOST` (default: localhost) (Eventually we will replace this with a VPN tunnel through the UCO network, once we recieve a static IP for the RPI5.)
  - `FOBOS_STREAM_PORT` (default: 8765)
- The deployment target is Linux; development on macOS is supported with the
  vendored `vmbpy-1.0.4-py3-none-any.whl` and Vimba X SDK installed
- Hardware config (`~/.jaeger.yaml`) must exist before running against real
  hardware
- Positioner centers for PIDs 1403 and 967 are **hardcoded** in
  `MainWindow.on_fps_ready`. The centers are determined by your setup. 
  so the hardcoded values are the correct permanent approach. Any new
  positioner must have its physical center added here manually.
  [TODO] Make document explaining camera calibration and positioner setup. 

---

## What is not yet implemented

- **`VimbaWorker.set_exposure()` / `set_gain()`** — the `@Slot` handlers exist
  and are wired to the `CameraWidget` camera settings panel, but the bodies
  only `print()`. Actual vmbpy camera property calls are TODO.
- **Positioner selection from the camera view before calibration** — if no
  calibration exists, `CameraWidget` shows a warning dialog and blocks clicks.
  A pre-calibration mode for positioner identification could be useful.