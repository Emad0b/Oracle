"""Opt-in, read-only background checks while the application is running."""
import threading


class BackgroundMonitor:
    def __init__(self, check, notify, interval=300):
        if interval < 30:
            raise ValueError("Minimum interval is 30 seconds")
        self.check, self.notify, self.interval = check, notify, interval
        self._stop = threading.Event()
        self._thread = None
        self._previous = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="oracle-monitor")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()

    def tick(self):
        try:
            current = self.check()
        except Exception:
            current = "Background check unavailable; verify the integration connection."
        if self._stop.is_set():
            return
        if current != self._previous:
            self._previous = current
            self.notify(current)

    def _run(self):
        while not self._stop.is_set():
            self.tick()
            if self._stop.wait(self.interval):
                break
