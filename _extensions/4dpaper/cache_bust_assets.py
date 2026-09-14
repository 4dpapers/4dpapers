#!/usr/bin/env python3
"""Quarto post-render hook: add version keys to local image URLs."""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote

_project_root = Path(
    os.environ.get("QUARTO_PROJECT_DIR")
    or os.environ.get("PROJECT_ROOT")
    or str(Path.cwd())
)

_IMG_SRC_RE = re.compile(
    r'(<img\b[^>]*\bsrc=")([^"#?]+(?:\.(?:png|jpe?g|gif|webp|svg)))(")',
    re.IGNORECASE,
)


def _output_dir() -> Path:
    return _project_root / "_output"


def _asset_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _resolve_asset(html_path: Path, src: str) -> Path | None:
    if re.match(r"^[a-z][a-z0-9+.-]*:", src, re.IGNORECASE) or src.startswith("//"):
        return None

    if src.startswith("/"):
        candidate = _project_root / src.lstrip("/")
        return candidate if candidate.exists() else None

    candidates = [
        (html_path.parent / src).resolve(),
        (_project_root / src).resolve(),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def cache_bust_html(html_path: Path) -> bool:
    content = html_path.read_text(encoding="utf-8")
    changed = False

    def repl(match: re.Match) -> str:
        nonlocal changed
        prefix, src, suffix = match.groups()
        asset = _resolve_asset(html_path, src)
        if asset is None:
            return match.group(0)

        changed = True
        return f'{prefix}{src}?v={quote(_asset_hash(asset))}{suffix}'

    new_content = _IMG_SRC_RE.sub(repl, content)
    if changed and new_content != content:
        html_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def main() -> int:
    # Paperview output feeds WeasyPrint; keep those asset URLs plain file paths.
    if os.environ.get("FOURD_PAPER_VIEW") == "1":
        return 0

    output_dir = _output_dir()
    if not output_dir.exists():
        print(f"No output directory at {output_dir} - skipping asset cache busting.", file=sys.stderr)
        return 0

    updated = 0
    for html_path in sorted(output_dir.rglob("*.html")):
        try:
            if cache_bust_html(html_path):
                updated += 1
        except Exception as exc:
            print(f"Error cache-busting assets in {html_path}: {exc}", file=sys.stderr)

    if updated:
        print(f"Cache-busted local image URLs in {updated} HTML file(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
