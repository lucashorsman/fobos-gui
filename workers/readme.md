Workers are background threads responsible for any operation that could block the UI. In PySide6, all UI rendering happens on the main thread, and if that thread gets tied up waiting on hardware — a camera frame, a positioner move that takes 30 seconds — the entire window freezes. Workers prevent that.
Each worker is a QThread subclass that owns one external resource:

VimbaWorker owns the camera session. It runs the vmbpy streaming loop and emits a frame_ready signal each time a new frame arrives.
PositionerWorker owns the positioner API connection. It receives move commands via slots and emits signals when a move completes, the position updates, or an error occurs.

The key idea is that workers and the UI never share data directly. They communicate exclusively through Qt signals and slots, which handle the thread boundary safely. The worker emits a signal, Qt queues it onto the main thread's event loop, and the UI updates — all without any manual locking or thread synchronization.
From the UI's perspective, clicking "go to position" just emits a signal and returns immediately. The actual blocking work happens on the worker thread in the background, and when it's done the worker fires back a signal to say so.
