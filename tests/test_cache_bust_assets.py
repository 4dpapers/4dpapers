"""Regression tests for post-render cache busting of local image assets."""
from __future__ import annotations

import importlib
import pathlib
import subprocess
from pathlib import Path

import pytest

from fourdpaper import cache_bust_assets

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def cache_bust(monkeypatch, tmp_path):
    monkeypatch.setenv("PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("QUARTO_PROJECT_DIR", raising=False)
    monkeypatch.delenv("FOURD_PAPER_VIEW", raising=False)
    return importlib.reload(cache_bust_assets)


def test_local_png_src_gets_content_hash_version(cache_bust, tmp_path):
    output = tmp_path / "_output"
    media = output / "media"
    media.mkdir(parents=True)
    (media / "figure.png").write_bytes(b"first-image")
    html = output / "paper.html"
    html.write_text('<img src="media/figure.png">', encoding="utf-8")

    assert cache_bust.main() == 0
    first = html.read_text(encoding="utf-8")
    assert 'src="media/figure.png?v=' in first

    first_version = first.split("?v=", 1)[1].split('"', 1)[0]
    html.write_text('<img src="media/figure.png">', encoding="utf-8")
    (media / "figure.png").write_bytes(b"replacement-image")

    assert cache_bust.main() == 0
    second = html.read_text(encoding="utf-8")
    second_version = second.split("?v=", 1)[1].split('"', 1)[0]
    assert second_version != first_version


def test_remote_and_already_versioned_images_are_left_alone(cache_bust, tmp_path):
    output = tmp_path / "_output"
    output.mkdir()
    html = output / "paper.html"
    html.write_text(
        '<img src="https://example.com/a.png"><img src="media/b.png?v=old">',
        encoding="utf-8",
    )

    assert cache_bust.main() == 0
    assert html.read_text(encoding="utf-8") == (
        '<img src="https://example.com/a.png"><img src="media/b.png?v=old">'
    )


def test_paperview_skips_cache_busting(cache_bust, tmp_path, monkeypatch):
    monkeypatch.setenv("FOURD_PAPER_VIEW", "1")
    output = tmp_path / "_output"
    media = output / "media"
    media.mkdir(parents=True)
    (media / "figure.png").write_bytes(b"png")
    html = output / "paper-paperview.html"
    html.write_text('<img src="media/figure.png">', encoding="utf-8")

    assert cache_bust.main() == 0
    assert html.read_text(encoding="utf-8") == '<img src="media/figure.png">'


def test_cache_bust_hook_registered_in_all_project_templates():
    """Every tracked Quarto project template must register the hook.

    Discovered via git rather than hardcoded: a hardcoded list previously
    referenced examples/heart/, which is gitignored, so the test could only
    pass on one machine.
    """
    tracked = subprocess.run(
        ["git", "ls-files", "*_quarto.yml"],
        cwd=_REPO, capture_output=True, text=True, check=True,
    ).stdout.split()
    project_files = [_REPO / p for p in tracked if pathlib.PurePosixPath(p).name == "_quarto.yml"]

    assert project_files, "no tracked _quarto.yml project templates found"

    for path in project_files:
        text = path.read_text(encoding="utf-8")
        assert "_extensions/4dpaper/cache_bust_assets.py" in text, path

    entrypoint = (_REPO / "docker-entrypoint.sh").read_text(encoding="utf-8")
    assert entrypoint.count("_extensions/4dpaper/cache_bust_assets.py") >= 2
