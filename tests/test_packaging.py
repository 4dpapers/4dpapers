"""The project must be importable as a package, with no sys.path surgery."""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Match actual statements, not prose that happens to mention "sys.path" (e.g.
# this module's own docstring above) or "spec_from_file_location" in a
# comment. Scoped to tests/test_*.py, which excludes conftest.py by
# construction - conftest.py holds the one legitimate importlib load.
_SYS_PATH_EDIT_RE = re.compile(r"^\s*sys\.path\.(insert|append)", re.MULTILINE)
_SPEC_FROM_FILE_LOCATION_RE = re.compile(r"spec_from_file_location\(")


def test_no_importlib_shims_in_test_modules():
    """Shims regenerate quietly - v0.1.3 added two while the cause was unfixed.

    conftest.py is exempt: it holds the single unavoidable load of
    4dpaper.py, which is a script and cannot be imported by name.
    """
    offenders = [
        str(p) for p in pathlib.Path("tests").rglob("test_*.py")
        if _SPEC_FROM_FILE_LOCATION_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"importlib shims remain in: {offenders}"


def test_no_sys_path_manipulation_in_tests():
    """A substring check on 'sys.path' would flag this file's own docstring.

    Matching the actual statement form (and scoping to test_*.py) avoids
    that false positive while still catching real sys.path surgery.
    """
    offenders = [
        str(p) for p in pathlib.Path("tests").rglob("test_*.py")
        if _SYS_PATH_EDIT_RE.search(p.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"sys.path edits remain in: {offenders}"


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
