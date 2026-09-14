"""Tests for the live file sync WebSocket plugin."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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


def _run_on_modified(root: Path, target: Path):
    """Fire on_modified for *target* with _PROJECT_ROOT patched to *root*.

    on_modified consults both ``sync_plugin._PROJECT_ROOT`` (its own
    traversal guard) and, via ``_is_write_allowed``, ``file_plugin._PROJECT_ROOT``
    (a separate module-level constant) -- both must be patched or the write
    allowlist check falls back to the real project root and reports
    "path traversal detected" for every tmp_path file.

    The IOLoop is mocked so on_modified's ``IOLoop.current().add_callback(...)``
    call can be inspected synchronously, without needing a running event loop.
    Returns the mocked ``add_callback`` for assertions.
    """
    import dashboard.sync_plugin as sp
    import dashboard.file_plugin as fp
    handler = sp.ProjectFileEventHandler()
    event = MagicMock(is_directory=False, src_path=str(target))
    mock_loop = MagicMock()
    with patch.object(sp, "_PROJECT_ROOT", root), \
         patch.object(fp, "_PROJECT_ROOT", root), \
         patch("tornado.ioloop.IOLoop.current", return_value=mock_loop):
        handler.on_modified(event)
    return mock_loop.add_callback


def test_on_modified_broadcasts_editable_file_with_exact_content(tmp_path):
    """The one path with zero prior coverage: a normal file must actually broadcast.

    Without this, every negative case below could pass for the wrong reason
    (nothing ever broadcasts, filters or not).
    """
    import dashboard.sync_plugin as sp
    root = tmp_path.resolve()
    target = root / "main.qmd"
    body = "# Title\n\nSome prose about the paper."
    target.write_text(body, encoding="utf-8")

    add_callback = _run_on_modified(root, target)

    add_callback.assert_called_once()
    fn, rel_path, content = add_callback.call_args[0]
    assert fn is sp._broadcast_file_change
    assert rel_path == "main.qmd"
    assert content == body


@pytest.mark.parametrize(
    "filename,content",
    [
        # Dotfile -- blocked by _should_include (path.name.startswith(".")).
        (".env", "API_KEY=super-secret"),
        # Secret-suffix filename -- blocked by _HIDDEN_SECRET_SUFFIXES.
        ("server.pem", "-----BEGIN PRIVATE KEY-----"),
        # Explicitly hidden filename -- blocked by _HIDDEN_FILE_NAMES.
        ("_shortcuts.yml", "shortcuts:\n  hpc: {path: /mnt/hpc}"),
        # Disallowed extension -- blocked by _WRITE_ALLOWED_EXTENSIONS.
        ("figure.png", "not actually png bytes, just needs to exist"),
    ],
)
def test_on_modified_blocks_secrets_and_disallowed_files(tmp_path, filename, content):
    root = tmp_path.resolve()
    target = root / filename
    target.write_text(content, encoding="utf-8")

    add_callback = _run_on_modified(root, target)

    add_callback.assert_not_called()


def test_on_modified_swallows_unreadable_file_without_raising(tmp_path):
    """A path that passes the filters but can't be read must not broadcast

    and must not propagate the read error out of on_modified.
    """
    root = tmp_path.resolve()
    missing = root / "ghost.qmd"  # never created -> read_text() raises

    add_callback = _run_on_modified(root, missing)

    add_callback.assert_not_called()
