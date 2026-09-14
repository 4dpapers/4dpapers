"""
Dashboard plugin: Real-time file synchronization via WebSockets and Watchdog.

Routes:
  GET /api/sync   — WebSocket endpoint for file change notifications
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import tornado.websocket
import tornado.ioloop
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from dashboard.auth import SecureMixin, _ALLOWED_ORIGIN
from dashboard.file_plugin import _should_include, _is_write_allowed

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))

# Global set of connected WebSockets
_clients = set()


class ProjectFileEventHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Check if the file is within our project root
        if not path.resolve().is_relative_to(_PROJECT_ROOT.resolve()):
            return

        # Ignore files we shouldn't include in the UI (like __pycache__, .git, etc.)
        if not _should_include(path):
            return

        # We only want to push updates for editable text-like files,
        # so we can use _is_write_allowed as a heuristic (which checks extensions).
        allowed, _ = _is_write_allowed(path)
        if not allowed:
            return

        # Attempt to read the file content
        try:
            content = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug(f"Failed to read modified file {path}: {exc}")
            return

        rel_path = str(path.relative_to(_PROJECT_ROOT))

        # We must schedule the write on the main Tornado IOLoop thread
        # because watchdog runs on its own background thread.
        try:
            io_loop = tornado.ioloop.IOLoop.current()
            io_loop.add_callback(_broadcast_file_change, rel_path, content)
        except RuntimeError:
            pass


def _broadcast_file_change(rel_path: str, content: str):
    if not _clients:
        return

    message = json.dumps({
        "event": "file_modified",
        "path": rel_path,
        "content": content
    })

    for client in list(_clients):
        try:
            client.write_message(message)
        except Exception as exc:
            logger.error(f"Failed to send to client: {exc}")


class FileSyncWebSocket(SecureMixin, tornado.websocket.WebSocketHandler):
    """WebSocket handler for real-time file updates."""

    def check_origin(self, origin: str) -> bool:
        """Reject cross-site WebSocket handshakes.

        Without this, any page the user visits can open a socket to the
        dashboard and receive every file they edit, because local-dev mode
        has no API key to withhold.
        """
        return origin == _ALLOWED_ORIGIN

    def prepare(self):
        # Authenticate before upgrading the connection to a WebSocket
        if not self.check_auth():
            return
        super().prepare()

    def open(self):
        _clients.add(self)
        logger.info(f"WebSocket client connected. Total clients: {len(_clients)}")

    def on_message(self, message):
        pass

    def on_close(self):
        if self in _clients:
            _clients.remove(self)
            logger.info(f"WebSocket client disconnected. Total clients: {len(_clients)}")


_observer = None


def start_observer() -> None:
    """Begin watching PROJECT_ROOT. Called by serve.py, not at import."""
    global _observer
    if _observer is not None:
        return

    _observer = Observer()
    _observer.schedule(ProjectFileEventHandler(), str(_PROJECT_ROOT), recursive=True)
    _observer.start()
    logger.info("Started watchdog file observer on %s", _PROJECT_ROOT)


def stop_observer() -> None:
    """Stop the watcher. Used by tests and on shutdown."""
    global _observer
    if _observer is None:
        return
    _observer.stop()
    _observer.join(timeout=5)
    _observer = None


__all__ = ["FileSyncWebSocket", "ROUTES", "start_observer", "stop_observer"]

ROUTES = [
    (r"/api/sync", FileSyncWebSocket),
]
