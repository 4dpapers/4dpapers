"""Tests for export-specific compile helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("tornado")


def test_validate_standalone_html_rejects_state_figure_references(tmp_path):
    from dashboard.compile_plugin import _validate_standalone_html_output

    html = tmp_path / "paper.html"
    html.write_text('<iframe src="../state/figures/fig-vm.html"></iframe>', encoding="utf-8")

    with pytest.raises(ValueError, match="state/figures"):
        _validate_standalone_html_output(html)


def test_validate_standalone_html_accepts_inlined_export(tmp_path):
    from dashboard.compile_plugin import _validate_standalone_html_output

    html = tmp_path / "paper.html"
    html.write_text('<iframe srcdoc="<html><body>ok</body></html>"></iframe>', encoding="utf-8")

    _validate_standalone_html_output(html)


def test_validate_paperview_html_rejects_missing_asset(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    output_dir = tmp_path / "_output"
    output_dir.mkdir()
    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="../state/figures/fig-vm.png">', encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="fig-vm.png"):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_accepts_app_root_state_asset(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output
    from unittest.mock import patch

    project_root = tmp_path / "project"
    output_dir = project_root / "_output"
    figures_dir = project_root / "state" / "figures"
    output_dir.mkdir(parents=True)
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig-vm.png").write_bytes(b"png")

    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="/state/figures/fig-vm.png">', encoding="utf-8")

    with patch("dashboard.compile_plugin._PROJECT_ROOT", project_root):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_accepts_versioned_state_asset(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output
    from unittest.mock import patch

    project_root = tmp_path / "project"
    output_dir = project_root / "_output"
    figures_dir = project_root / "state" / "figures"
    output_dir.mkdir(parents=True)
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig-vm.png").write_bytes(b"png")

    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="/state/figures/fig-vm.png?v=abc123">', encoding="utf-8")

    with patch("dashboard.compile_plugin._PROJECT_ROOT", project_root):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_rejects_remote_pdf_assets(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    html = tmp_path / "paper-paperview.html"
    html.write_text(
        '<img src="https://latex.codecogs.com/svg.latex?E%3Dmc%5E2">',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="remote assets"):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_allows_remote_pdf_assets_when_enabled(tmp_path, monkeypatch):
    from dashboard.compile_plugin import _validate_paperview_html_output

    monkeypatch.setenv("FOURD_PDF_ALLOW_REMOTE", "1")
    html = tmp_path / "paper-paperview.html"
    html.write_text(
        '<img src="https://latex.codecogs.com/svg.latex?E%3Dmc%5E2">',
        encoding="utf-8",
    )

    _validate_paperview_html_output(html)


def test_validate_paperview_html_rejects_placeholder_warning(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    html = tmp_path / "paper-paperview.html"
    html.write_text("⚠ Figure <code>fig-vm</code> not rendered — click Rebuild HTML", encoding="utf-8")

    with pytest.raises(ValueError, match="Static figure generation failed"):
        _validate_paperview_html_output(html)


def test_validate_paperview_html_accepts_existing_assets(tmp_path):
    from dashboard.compile_plugin import _validate_paperview_html_output

    output_dir = tmp_path / "_output"
    figures_dir = tmp_path / "state" / "figures"
    output_dir.mkdir()
    figures_dir.mkdir(parents=True)
    (figures_dir / "fig-vm.png").write_bytes(b"png")

    html = output_dir / "paper-paperview.html"
    html.write_text('<img src="../state/figures/fig-vm.png">', encoding="utf-8")

    _validate_paperview_html_output(html)


def test_rewrite_paperview_asset_urls_for_pdf_converts_state_root_url():
    from dashboard.compile_plugin import _rewrite_paperview_asset_urls_for_pdf

    html = '<img src="/state/figures/fig-vm.png"><img src="../state/figures/fig-at.png">'
    rewritten = _rewrite_paperview_asset_urls_for_pdf(html)

    assert 'src="../state/figures/fig-vm.png"' in rewritten
    assert 'src="../state/figures/fig-at.png"' in rewritten


def test_rewrite_paperview_asset_urls_for_pdf_strips_cache_queries():
    from dashboard.compile_plugin import _rewrite_paperview_asset_urls_for_pdf

    html = '<img src="/state/figures/fig-vm.png?v=abc"><img src="../state/figures/fig-at.png?v=def">'
    rewritten = _rewrite_paperview_asset_urls_for_pdf(html)

    assert 'src="../state/figures/fig-vm.png"' in rewritten
    assert 'src="../state/figures/fig-at.png"' in rewritten
    assert "?v=" not in rewritten


def test_validate_native_pdf_output_accepts_valid_pdf(tmp_path):
    from dashboard.compile_plugin import _validate_native_pdf_output

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\n" + b"0" * 1200 + b"\n%%EOF\n")

    _validate_native_pdf_output(pdf)


def test_validate_native_pdf_output_rejects_missing_pdf(tmp_path):
    from dashboard.compile_plugin import _validate_native_pdf_output

    with pytest.raises(FileNotFoundError, match="PDF output not found"):
        _validate_native_pdf_output(tmp_path / "missing.pdf")


def test_validate_native_pdf_output_rejects_truncated_pdf(tmp_path):
    from dashboard.compile_plugin import _validate_native_pdf_output

    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7\nnot finished")

    with pytest.raises(ValueError, match="truncated|empty"):
        _validate_native_pdf_output(pdf)


def test_pdf_url_fetcher_blocks_remote_and_logs():
    """The offline PDF fetcher refuses remote URLs and records them in the log."""
    from dashboard.compile_plugin import _make_pdf_url_fetcher

    log: list[str] = []
    fetch = _make_pdf_url_fetcher(log)

    for url in (
        "http://example.com/a.png",
        "https://cdn.x/y.css",
        "https://fonts.googleapis.com/css2?family=Inter",
        "ftp://h/f",
    ):
        with pytest.raises(ValueError, match="[Rr]emote"):
            fetch(url)

    assert len(log) == 4
    assert all(
        "example.com" in m
        or "cdn.x" in m
        or "fonts.googleapis.com" in m
        or "ftp://h" in m
        for m in log
    )


def test_pdf_url_fetcher_allows_data_uri():
    """`data:` URIs are local content and must pass through to WeasyPrint."""
    pytest.importorskip("weasyprint")
    from dashboard.compile_plugin import _make_pdf_url_fetcher

    log: list[str] = []
    fetch = _make_pdf_url_fetcher(log)
    # A 1x1 transparent PNG data URI — the default fetcher decodes it locally.
    data_uri = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42m"
        "NkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    result = fetch(data_uri)  # must not raise; return shape varies by version
    assert result is not None
    assert log == []


def test_pdf_url_fetcher_opt_in_allows_remote(monkeypatch):
    """FOURD_PDF_ALLOW_REMOTE escape hatch lets remote URLs reach the default fetcher."""
    weasyprint = pytest.importorskip("weasyprint")
    from dashboard.compile_plugin import _make_pdf_url_fetcher

    # Stub the default fetcher so we prove delegation happens without any network.
    seen: list[str] = []
    monkeypatch.setattr(
        weasyprint,
        "default_url_fetcher",
        lambda url, *a, **k: seen.append(url) or {"string": b"", "mime_type": "text/plain"},
    )

    log: list[str] = []
    fetch = _make_pdf_url_fetcher(log, allow_remote=True)
    fetch("http://example.com/remote.png")

    assert seen == ["http://example.com/remote.png"]  # delegated, not blocked
    assert log == []


def test_pdf_render_with_remote_reference_does_not_hang():
    """A paper referencing an unreachable remote asset still renders a valid PDF fast.

    The remote host (a TEST-NET address that black-holes connections) would hang
    WeasyPrint's default fetcher on a connect timeout — the original silent
    'PDF export does nothing' symptom. With the offline fetcher the reference is
    dropped and the render completes near-instantly.
    """
    import time

    weasyprint = pytest.importorskip("weasyprint")
    from dashboard.compile_plugin import _make_pdf_url_fetcher

    html = (
        '<html><body><h1>Sentinel</h1>'
        '<img src="http://192.0.2.1/never.png">'
        '<link rel="stylesheet" href="http://192.0.2.1/never.css">'
        '</body></html>'
    )
    log: list[str] = []
    fetcher = _make_pdf_url_fetcher(log)

    t0 = time.monotonic()
    pdf = weasyprint.HTML(string=html, url_fetcher=fetcher).write_pdf()
    elapsed = time.monotonic() - t0

    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 500
    assert elapsed < 15, f"render took {elapsed:.1f}s — remote fetch likely hung"
    assert any("192.0.2.1" in m for m in log)

