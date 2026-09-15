"""Shared fixtures."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / "_extensions" / "4dpaper" / "4dpaper.py"


@pytest.fixture(scope="session")
def fourdpaper_hook():
    """The Quarto pre-render hook, loaded by path.

    This is the ONE legitimate importlib load in the suite. The hook is a
    script whose module name would be `4dpaper` — not a valid Python
    identifier — so it cannot be imported by name however the package is
    laid out. Every other module is a normal import.
    """
    spec = importlib.util.spec_from_file_location("fourdpaper_hook", HOOK_PATH)
    assert spec and spec.loader, f"cannot load {HOOK_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
