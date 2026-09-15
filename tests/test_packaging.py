"""The project must be importable as a package, with no sys.path surgery."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _import_ok(statement: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", statement],
        capture_output=True, text=True, cwd=str(cwd),
    )


def _assert_all_under_repo_root(stdout: str) -> None:
    lines = [line for line in stdout.strip().splitlines() if line]
    assert lines, "expected at least one printed __file__ path"
    for line in lines:
        resolved = Path(line).resolve()
        assert resolved.is_relative_to(_REPO_ROOT), (
            f"{resolved} does not resolve under the repository root {_REPO_ROOT}"
        )


def test_library_modules_import_in_a_fresh_interpreter(tmp_path):
    """Thirteen importlib shims exist in the suite only because this failed.

    Runs with cwd=tmp_path so nothing can be imported by accident from the
    repo working directory, and checks WHERE each module resolved from -
    only a real install of this package (not some other checkout) can
    satisfy both.
    """
    out = _import_ok(
        "import fourdpaper.lib.render as r;"
        "import fourdpaper.lib.parser as p;"
        "import fourdpaper.export_templates as e;"
        "print(r.__file__); print(p.__file__); print(e.__file__)",
        cwd=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    _assert_all_under_repo_root(out.stdout)


def test_sibling_packages_import(tmp_path):
    """Runs with cwd=tmp_path so 'dashboard' and 'scripts' cannot import
    from the working directory with no install at all, and checks WHERE
    each module resolved from - a stale install elsewhere must not pass.
    """
    out = _import_ok(
        "import dashboard.compile_plugin as d;"
        "import scripts.data_loader as s;"
        "print(d.__file__); print(s.__file__)",
        cwd=tmp_path,
    )
    assert out.returncode == 0, out.stderr
    _assert_all_under_repo_root(out.stdout)


def test_hook_guards_against_a_foreign_fourdpaper_install(tmp_path):
    """4dpaper.py must refuse to run if the imported 'fourdpaper' package
    resolves outside its own source tree (e.g. a stale editable install
    pointing at a different checkout) - otherwise figures would be silently
    built from the wrong copy of the code.

    Puts a decoy 'fourdpaper' package on PYTHONPATH ahead of the real
    installed one, so the hook's import resolves there instead, and
    verifies the hook detects the mismatch and exits 1 with an actionable
    message naming both locations.
    """
    decoy_root = tmp_path / "decoy_pythonpath"
    decoy_lib = decoy_root / "fourdpaper" / "lib"
    decoy_lib.mkdir(parents=True)
    (decoy_lib / "__init__.py").write_text("")
    # Only needs to satisfy the names imported before the guard runs.
    (decoy_lib / "config.py").write_text(
        "_project_root = None\n"
        "_app_root = None\n"
        "class ShortcutResolver:\n"
        "    pass\n"
        "_shortcut_resolver = None\n"
        "_shortcuts_yml_path = None\n"
    )

    hook_path = _REPO_ROOT / "_extensions" / "4dpaper" / "4dpaper.py"
    env = {**os.environ, "PYTHONPATH": str(decoy_root)}
    out = subprocess.run(
        [sys.executable, str(hook_path)],
        capture_output=True, text=True, cwd=str(_REPO_ROOT), env=env,
    )
    assert out.returncode == 1, (out.stdout, out.stderr)
    assert "different copy of the code" in out.stderr
    assert str(decoy_lib.resolve()) in out.stderr
