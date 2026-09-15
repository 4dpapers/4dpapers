"""The project must be importable as a package, with no sys.path surgery."""
from __future__ import annotations

import subprocess
import sys


def _import_ok(statement: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", statement],
                          capture_output=True, text=True)


def test_library_modules_import_in_a_fresh_interpreter():
    """Thirteen importlib shims exist in the suite only because this failed."""
    out = _import_ok(
        "import fourdpaper.lib.parser as p;"
        "import fourdpaper.lib.render as r;"
        "import fourdpaper.export_templates as e;"
        "print(p.__name__, r.__name__, e.__name__)"
    )
    assert out.returncode == 0, out.stderr


def test_sibling_packages_import():
    out = _import_ok(
        "import dashboard.compile_plugin;"
        "import scripts.data_loader;"
        "print('ok')"
    )
    assert out.returncode == 0, out.stderr
