#!/usr/bin/env python3
"""Render the deterministic launch animation in demo.html to an MP4."""

from __future__ import annotations

import argparse
import http.server
import shutil
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_URL_PATH = "/media/launch/demo.html"


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        pass


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def render(output: Path, fps: int) -> None:
    handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
        *args, directory=str(REPO_ROOT), **kwargs
    )
    server = ReusableTCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}{DEMO_URL_PATH}"

    try:
        with tempfile.TemporaryDirectory(prefix="4dpapers-demo-") as tmp:
            frame_dir = Path(tmp) / "frames"
            frame_dir.mkdir()

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(
                    viewport={"width": 1920, "height": 1080},
                    device_scale_factor=1,
                )
                page.goto(url, wait_until="load", timeout=120_000)
                page.wait_for_function("window.__ready === true", timeout=120_000)
                page.wait_for_function("paperReady === true", timeout=120_000)
                # Let vtk.js finish its first WebGL render before deterministic capture.
                page.wait_for_timeout(3_000)
                duration = float(page.evaluate("window.__DUR"))
                total = round(duration * fps)
                for frame in range(total):
                    page.evaluate("t => window.seek(t)", frame / fps)
                    page.screenshot(path=str(frame_dir / f"frame-{frame:05d}.png"))
                    if frame % fps == 0:
                        print(f"Rendered {frame // fps:2d}s / {duration:.1f}s", flush=True)
                browser.close()

            encoded = Path(tmp) / "4dpapers-demo.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-framerate",
                    str(fps),
                    "-i",
                    str(frame_dir / "frame-%05d.png"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-y",
                    str(encoded),
                ],
                check=True,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(encoded, output)
    finally:
        server.shutdown()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name("4dpapers-demo.mp4"),
    )
    parser.add_argument("--fps", type=int, default=30)
    args = parser.parse_args()
    render(args.output.resolve(), args.fps)
    print(f"Wrote {args.output.resolve()}")


if __name__ == "__main__":
    main()
