"""Tests for the live file sync WebSocket plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_sync_plugin_imports_without_starting_observer():
    """Importing the module must not spawn a filesystem watcher."""
    import dashboard.sync_plugin as sp
    assert sp._observer is None, "observer started at import time"
    assert len(sp.ROUTES) == 1
    assert sp.ROUTES[0][0] == r"/api/sync"


def test_check_origin_rejects_foreign_origin():
    from dashboard.sync_plugin import FileSyncWebSocket
    handler = FileSyncWebSocket.__new__(FileSyncWebSocket)
    assert handler.check_origin("https://evil.example.com") is False


def test_check_origin_accepts_configured_origin():
    from dashboard.sync_plugin import FileSyncWebSocket
    from dashboard.auth import _ALLOWED_ORIGIN
    handler = FileSyncWebSocket.__new__(FileSyncWebSocket)
    assert handler.check_origin(_ALLOWED_ORIGIN) is True


def test_broadcast_sends_json_to_every_client():
    import dashboard.sync_plugin as sp
    c1, c2 = MagicMock(), MagicMock()
    with patch.object(sp, "_clients", {c1, c2}):
        sp._broadcast_file_change("main.qmd", "# Title")
    for client in (c1, c2):
        client.write_message.assert_called_once()
        payload = json.loads(client.write_message.call_args[0][0])
        assert payload == {
            "event": "file_modified",
            "path": "main.qmd",
            "content": "# Title",
        }


def test_broadcast_survives_a_dead_client():
    """One broken socket must not stop delivery to the others."""
    import dashboard.sync_plugin as sp
    dead, alive = MagicMock(), MagicMock()
    dead.write_message.side_effect = RuntimeError("socket closed")
    with patch.object(sp, "_clients", {dead, alive}):
        sp._broadcast_file_change("a.qmd", "x")
    alive.write_message.assert_called_once()


def test_event_handler_ignores_paths_outside_project_root(tmp_path):
    import dashboard.sync_plugin as sp
    outside = tmp_path / "outside.qmd"
    outside.write_text("secret")
    handler = sp.ProjectFileEventHandler()
    event = MagicMock(is_directory=False, src_path=str(outside))
    with patch.object(sp, "_PROJECT_ROOT", Path("/nonexistent/project")), \
         patch.object(sp, "_broadcast_file_change") as bc:
        handler.on_modified(event)
    bc.assert_not_called()


def test_event_handler_ignores_directories():
    import dashboard.sync_plugin as sp
    handler = sp.ProjectFileEventHandler()
    event = MagicMock(is_directory=True, src_path="/whatever")
    with patch.object(sp, "_broadcast_file_change") as bc:
        handler.on_modified(event)
    bc.assert_not_called()
