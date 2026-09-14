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


def test_remote_image_in_source_blocks_pdf_export(tmp_path):
    """A remote image must be refused by name, not by pandoc traceback."""
    from dashboard.compile_plugin import _validate_no_remote_sources
    qmd = tmp_path / "paper.qmd"
    qmd.write_text("# T\n\n![fig](https://example.com/remote.png)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Remote resources are disabled"):
        _validate_no_remote_sources(qmd)


def test_local_image_in_source_allows_pdf_export(tmp_path):
    from dashboard.compile_plugin import _validate_no_remote_sources
    qmd = tmp_path / "paper.qmd"
    qmd.write_text("# T\n\n![fig](data/local.png)\n", encoding="utf-8")
    _validate_no_remote_sources(qmd)  # must not raise


def test_remote_image_allowed_when_opted_in(tmp_path, monkeypatch):
    from dashboard.compile_plugin import _validate_no_remote_sources
    monkeypatch.setenv("FOURD_PDF_ALLOW_REMOTE", "1")
    qmd = tmp_path / "paper.qmd"
    qmd.write_text("# T\n\n![fig](https://example.com/remote.png)\n", encoding="utf-8")
    _validate_no_remote_sources(qmd)  # must not raise
