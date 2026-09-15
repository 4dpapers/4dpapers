"""Tests for the HTML export template Tornado plugin (dashboard/template_plugin.py).

Follows the handler-construction pattern used across the dashboard test suite
(see tests/test_compile_plugin.py / tests/test_export_pipeline.py): build the
handler via ``Handler.__new__(Handler)``, stub ``request`` with a plain object
carrying ``body``/``headers``/``remote_ip``, and replace ``write``/``set_status``/
``set_header``/``finish`` with ``MagicMock``s so assertions can be made on them
without going through a live Tornado server.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytest.importorskip("tornado")

import dashboard.compile_plugin as compile_plugin
import dashboard.template_plugin as template_plugin
from dashboard.template_plugin import TemplateExportHandler, TEMPLATES


class _Req:
    """Minimal stand-in for tornado.httputil.HTTPServerRequest."""

    def __init__(self, body: bytes, remote_ip: str):
        self.body = body
        self.headers: dict[str, str] = {}
        self.remote_ip = remote_ip


def _make_handler(body: dict, remote_ip: str) -> TemplateExportHandler:
    handler = TemplateExportHandler.__new__(TemplateExportHandler)
    handler.request = _Req(json.dumps(body).encode("utf-8"), remote_ip)
    handler.check_auth = lambda: True
    handler.write = MagicMock()
    handler.set_status = MagicMock()
    handler.set_header = MagicMock()
    handler.finish = MagicMock()
    return handler


@pytest.fixture()
def rendered_project(tmp_path, monkeypatch):
    """A hermetic project root with a fake-but-successful render pipeline.

    The real `quarto` render is far too heavy for a handler-level unit test,
    so `run_quarto_render` is stubbed to just drop the standalone HTML file
    the handler expects to find afterwards. Everything downstream of that
    (signing, validation, template application) runs for real.
    """
    (tmp_path / "main.qmd").write_text("# Title\n\nBody text.\n", encoding="utf-8")
    (tmp_path / "_output").mkdir()

    monkeypatch.setattr(template_plugin, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(compile_plugin, "_PROJECT_ROOT", tmp_path)

    def _fake_render(qmd_path: Path, log_lines: list, output_format: str, csl):
        out = tmp_path / "_output" / f"{qmd_path.stem}-standalone.html"
        out.write_text(
            "<html><head><title>T</title></head><body>"
            "<main id=\"quarto-document-content\"><p>Body text.</p></main>"
            "</body></html>",
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(template_plugin, "run_quarto_render", _fake_render)
    return tmp_path


def test_unknown_template_returns_400(rendered_project):
    """A typo in a template name must not silently restyle the paper."""
    handler = _make_handler(
        {"target": "main.qmd", "template": "not-a-real-template"},
        remote_ip="10.77.0.1",
    )
    asyncio.run(handler.post())

    handler.set_status.assert_called_once_with(400)
    written = handler.write.call_args[0][0]
    assert "not-a-real-template" in written["error"]
    for name in TEMPLATES:
        assert name in written["error"]
    # Must not have fallen through to streaming a templated document.
    assert not any(
        call.args and isinstance(call.args[0], (bytes, bytearray))
        for call in handler.write.call_args_list
    )


def test_known_template_does_not_400(rendered_project):
    """Sanity check: a real template name must not be rejected."""
    handler = _make_handler(
        {"target": "main.qmd", "template": "academic"},
        remote_ip="10.77.0.2",
    )
    asyncio.run(handler.post())

    handler.set_status.assert_not_called()
    handler.finish.assert_called_once()
    written_bytes = b"".join(
        call.args[0]
        for call in handler.write.call_args_list
        if call.args and isinstance(call.args[0], (bytes, bytearray))
    )
    assert b"fourd-template-preset" in written_bytes
