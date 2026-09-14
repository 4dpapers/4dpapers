"""
Dashboard plugin: HTML export with template styling.

Routes:
  POST /api/export-with-template  — compile paperview HTML, apply a CSS
                                    template + optional figure index, and
                                    stream the result back for download.

  GET  /api/export-templates      — return available template names and their
                                    starter CSS (used by the template designer
                                    in the dashboard UI).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

import tornado.web

from dashboard.auth import SecureMixin
from dashboard.render_lock import _render_lock
from dashboard.utils import run_quarto_render, maybe_sign_rendered_html
from dashboard.compile_plugin import (
    _check_rate_limit,
    _MAX_COMPILE_BODY_BYTES,
    _resolve_target,
    _resolve_csl,
    _active_build_log,
    _validate_standalone_html_output,
)

# Import the template engine.  The extension lives at the project root, so we
# need to add its parent to sys.path before importing.
_PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", str(Path(__file__).parent.parent)))
_EXT_DIR = _PROJECT_ROOT / "_extensions" / "4dpaper"

if str(_EXT_DIR) not in sys.path:
    sys.path.insert(0, str(_EXT_DIR))

from export_templates import apply_template, TEMPLATES  # noqa: E402


class TemplateExportHandler(SecureMixin, tornado.web.RequestHandler):
    """POST /api/export-with-template

    Request body (JSON):
        {
          "files":      { "<path>": "<content>", … },   // unsaved editor files
          "target":     "main.qmd",                     // which paper to render
          "csl":        "numeric",                      // citation style key
          "template":   "modern",                       // preset name
          "custom_css": "body { … }",                   // extra CSS (optional)
          "add_index":  true                            // inject figure index?
        }

    Response:
        text/html — the templated, self-contained export HTML.
    """

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="POST, OPTIONS")

    def options(self) -> None:
        self.finish()

    async def post(self) -> None:
        if not self.check_auth():
            return

        client_ip = (
            self.request.headers.get("X-Forwarded-For", self.request.remote_ip)
            .split(",")[0]
            .strip()
        )
        if not _check_rate_limit(client_ip):
            self.set_status(429)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "Too many requests. Please wait a minute before exporting again."})
            return

        try:
            if len(self.request.body) > _MAX_COMPILE_BODY_BYTES:
                self.set_status(413)
                self.set_header("Content-Type", "application/json")
                self.write({"error": "Request body exceeds 50 MB limit"})
                return

            body = json.loads(self.request.body) if self.request.body else {}
        except json.JSONDecodeError as exc:
            self.set_status(400)
            self.set_header("Content-Type", "application/json")
            self.write({"error": f"Invalid JSON: {exc}"})
            return

        # ── Save any in-flight editor files ──────────────────────────────────
        from dashboard.file_plugin import _is_write_allowed

        files_to_save = body.get("files", {})
        for file_path_str, content in files_to_save.items():
            if len(content.encode("utf-8", errors="replace")) > 10 * 1024 * 1024:
                self.set_status(413)
                self.set_header("Content-Type", "application/json")
                self.write({"error": f"File '{file_path_str}' exceeds 10 MB limit"})
                return

            path = (_PROJECT_ROOT / file_path_str).resolve()
            allowed, reason = _is_write_allowed(_PROJECT_ROOT / file_path_str)
            if not allowed:
                self.set_status(403)
                self.set_header("Content-Type", "application/json")
                self.write({"error": f"Write denied for '{file_path_str}': {reason}"})
                return

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

        # ── Resolve rendering target ──────────────────────────────────────────
        main_qmd = _resolve_target(body)
        if not main_qmd.exists():
            self.set_status(404)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "Main QMD file not found"})
            return

        csl_path = _resolve_csl(body)

        # ── Run html-export render (interactive figures) ──────────────────────
        _active_build_log.clear()
        log_lines: list[str] = _active_build_log
        loop = asyncio.get_event_loop()
        async with _render_lock:
            exit_code = await loop.run_in_executor(
                None, run_quarto_render, main_qmd, log_lines, "html-export", csl_path
            )

        if exit_code != 0:
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({
                "error": "Compilation failed",
                "exit_code": exit_code,
                "log": "\n".join(log_lines[-50:]),
            })
            return

        # ── Locate the rendered standalone HTML ──────────────────────────────
        stem = main_qmd.stem
        html_path = _PROJECT_ROOT / "_output" / f"{stem}-standalone.html"

        # Wait briefly for Quarto to flush
        import time
        for _ in range(6):
            if html_path.exists():
                break
            time.sleep(0.5)

        if not html_path.exists():
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "Standalone HTML not found after render"})
            return

        maybe_sign_rendered_html(html_path, log_lines)
        _validate_standalone_html_output(html_path)

        html_text = html_path.read_text(encoding="utf-8")

        # ── Apply template ───────────────────────────────────────────────────
        template_name = body.get("template", "academic")
        if template_name not in TEMPLATES:
            template_name = "academic"

        custom_css = body.get("custom_css") or None
        add_index = bool(body.get("add_index", False))

        final_html = apply_template(
            html_text,
            template=template_name,
            custom_css=custom_css,
            add_index=add_index,
        )

        # ── Stream back as downloadable HTML ─────────────────────────────────
        download_name = f"{stem}-{template_name}.html"
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.set_header(
            "Content-Disposition",
            f'attachment; filename="{download_name}"',
        )
        self.write(final_html.encode("utf-8"))
        self.finish()


class TemplateListHandler(SecureMixin, tornado.web.RequestHandler):
    """GET /api/export-templates

    Returns a JSON object listing available templates and their starter CSS:
        {
          "templates": {
            "academic": "/* CSS … */",
            "modern":   "/* CSS … */",
            …
          }
        }
    """

    def set_default_headers(self) -> None:
        self.apply_cors_headers(methods="GET, OPTIONS")
        self.set_header("Content-Type", "application/json")

    def options(self) -> None:
        self.finish()

    def get(self) -> None:
        if not self.check_auth():
            return
        self.write(json.dumps({"templates": TEMPLATES}))


ROUTES = [
    (r"/api/export-with-template", TemplateExportHandler),
    (r"/api/export-templates", TemplateListHandler),
]
