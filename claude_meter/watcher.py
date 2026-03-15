"""Watch ~/.claude/ for changes and trigger refresh callbacks."""

import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

WATCH_EXTENSIONS = {".jsonl", ".json"}


class ClaudeFileHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def on_modified(self, event):
        if event.is_directory:
            return
        ext = Path(event.src_path).suffix
        if ext in WATCH_EXTENSIONS:
            self.callback()


class ClaudeWatcher:
    """Watches the Claude data directory for file changes."""

    def __init__(self, claude_dir: Path, on_change):
        self._observer = Observer()
        self._handler = ClaudeFileHandler(on_change)
        self._path = str(claude_dir)
        self._thread = None

    def start(self):
        try:
            # Watch recursively to catch projects/<path>/<session>.jsonl changes
            self._observer.schedule(self._handler, self._path, recursive=True)
            self._observer.daemon = True
            self._observer.start()
        except Exception:
            pass  # Fail silently — timer refresh is the fallback

    def stop(self):
        try:
            self._observer.stop()
            self._observer.join(timeout=2)
        except Exception:
            pass
