"""The project must be importable as a package, with no sys.path surgery."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFTEST_PATH = _REPO_ROOT / "tests" / "conftest.py"

# Names whose mere presence (as an attribute, a bare name after `from ... import
# ...`, or the target of an import) marks a legitimate-but-single-use module
# loading shim. conftest.py's `fourdpaper_hook` fixture is the one allowed use;
# everywhere else these mean the shim regrew.
_SHIM_LOADER_NAMES = {"spec_from_file_location", "SourceFileLoader"}


def _find_shims(source: str) -> list[str]:
    """Parse `source` with the AST and return one description per violation.

    Using the AST instead of regex means comments and docstrings can't
    produce false positives, and the usual regex evasions (aliasing `sys`,
    slice/augmented assignment to `sys.path`, `monkeypatch.syspath_prepend`,
    an aliased or getattr'd `spec_from_file_location`/`SourceFileLoader`,
    bare `lib` imports, and `importlib.import_module("lib...")`) can't slip
    past it either, because every one of those still produces the same AST
    node shapes this walks for.
    """
    tree = ast.parse(source)
    findings: list[str] = []

    sys_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "sys":
                    sys_aliases.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                node.attr == "path"
                and isinstance(node.value, ast.Name)
                and node.value.id in sys_aliases
            ):
                findings.append(f"{node.lineno}: sys.path access via '{node.value.id}.path'")
            elif node.attr == "syspath_prepend":
                findings.append(f"{node.lineno}: .syspath_prepend(...) attribute access")
            elif node.attr in _SHIM_LOADER_NAMES:
                findings.append(f"{node.lineno}: '{node.attr}' accessed as an attribute")

        elif isinstance(node, ast.Name):
            if node.id == "syspath_prepend":
                findings.append(f"{node.lineno}: bare name 'syspath_prepend'")
            elif node.id in _SHIM_LOADER_NAMES:
                findings.append(f"{node.lineno}: bare name '{node.id}'")

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "sys":
                for alias in node.names:
                    if alias.name == "path":
                        findings.append(f"{node.lineno}: from sys import path")
            for alias in node.names:
                if alias.name in _SHIM_LOADER_NAMES:
                    findings.append(f"{node.lineno}: from {module} import {alias.name}")
            if module == "lib" or module.startswith("lib."):
                findings.append(f"{node.lineno}: from {module} import ...")

        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "lib" or alias.name.startswith("lib."):
                    findings.append(f"{node.lineno}: import {alias.name}")

        elif isinstance(node, ast.Call):
            func = node.func
            is_import_module = (
                (isinstance(func, ast.Name) and func.id == "import_module")
                or (isinstance(func, ast.Attribute) and func.attr == "import_module")
            )
            if is_import_module and node.args:
                first = node.args[0]
                if (
                    isinstance(first, ast.Constant)
                    and isinstance(first.value, str)
                    and (first.value == "lib" or first.value.startswith("lib."))
                ):
                    findings.append(f"{node.lineno}: import_module({first.value!r})")

            if isinstance(func, ast.Name) and func.id == "getattr":
                for arg in node.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value in _SHIM_LOADER_NAMES
                    ):
                        findings.append(f"{node.lineno}: getattr(..., {arg.value!r})")

    return findings


def test_no_import_shims_in_tests():
    """Shims regenerate quietly - v0.1.3 added two while the cause was unfixed,
    and syspath_prepend slipped a further two past the old regex guards.

    Scans every *.py under tests/ (conftest.py, tests/__init__.py and
    tests/data/*.py included - the old guards only looked at test_*.py) from
    the absolute repo root, so running pytest from inside tests/ can't make
    the glob find nothing and pass vacuously the way the old relative
    Path("tests") did.

    conftest.py is exempt for exactly one spec_from_file_location use: the
    single unavoidable load of 4dpaper.py, which is a script and cannot be
    imported by name. Any other finding in conftest.py - a second shim, a
    sys.path edit, anything - still fails the test.
    """
    test_files = sorted((_REPO_ROOT / "tests").rglob("*.py"))
    assert len(test_files) >= 30, (
        f"expected to scan at least 30 files under {_REPO_ROOT / 'tests'}, "
        f"found {len(test_files)} - the scan may not be visiting files"
    )

    offenders: list[str] = []
    for path in test_files:
        findings = _find_shims(path.read_text(encoding="utf-8"))

        if path == _CONFTEST_PATH:
            exempted = False
            remaining = []
            for finding in findings:
                if not exempted and "spec_from_file_location" in finding:
                    exempted = True
                    continue
                remaining.append(finding)
            findings = remaining

        rel = path.relative_to(_REPO_ROOT)
        offenders.extend(f"{rel}:{finding}" for finding in findings)

    assert not offenders, "import shims found:\n" + "\n".join(offenders)


_SHIM_EVASIONS = [
    ("import sys\nsys.path.insert(0, 'x')\n", True, "sys.path.insert"),
    ("import sys\nsys.path.append('x')\n", True, "sys.path.append"),
    ("import sys\nsys.path[0:0] = ['x']\n", True, "sys.path slice assignment"),
    ("import sys\nsys.path += ['x']\n", True, "sys.path augmented assignment"),
    ("import sys\nsys.path.extend(['x'])\n", True, "sys.path.extend"),
    ("import sys\nsys.path = ['x']\n", True, "sys.path plain assignment"),
    ("import sys as s\ns.path.insert(0, 'x')\n", True, "aliased sys"),
    ("import sys; sys.path.insert(0, 'x')\n", True, "statement after semicolon"),
    (
        "def f(monkeypatch):\n    monkeypatch.syspath_prepend('x')\n",
        True,
        "monkeypatch.syspath_prepend",
    ),
    (
        "from importlib.util import spec_from_file_location\n",
        True,
        "spec_from_file_location import",
    ),
    (
        "from importlib.util import spec_from_file_location as sffl\n",
        True,
        "aliased spec_from_file_location import",
    ),
    (
        "from importlib.machinery import SourceFileLoader\n",
        True,
        "SourceFileLoader import",
    ),
    (
        "import importlib.util\nimportlib.util.spec_from_file_location('x', 'y')\n",
        True,
        "spec_from_file_location as attribute",
    ),
    (
        "import importlib.util\n"
        "getattr(importlib.util, 'spec_from_file_location')('x', 'y')\n",
        True,
        "spec_from_file_location reached via getattr",
    ),
    ("import lib\n", True, "bare import lib"),
    ("import lib.x\n", True, "bare import lib.x"),
    ("from lib import render\n", True, "from lib import ..."),
    ("from lib.x import render\n", True, "from lib.x import ..."),
    (
        "import importlib\nimportlib.import_module('lib')\n",
        True,
        "importlib.import_module('lib')",
    ),
    (
        "import importlib\nimportlib.import_module('lib.x')\n",
        True,
        "importlib.import_module('lib.x')",
    ),
    (
        "from importlib import import_module\nimport_module('lib')\n",
        True,
        "bare import_module('lib')",
    ),
    (
        '"""Mentions sys.path.insert in a docstring, not as code."""\n',
        False,
        "docstring mention",
    ),
    (
        "# a comment mentioning spec_from_file_location(\nx = 1\n",
        False,
        "comment mention",
    ),
    ("from fourdpaper.lib import render\n", False, "fourdpaper.lib is not lib"),
    ("import pathlib\n", False, "pathlib is not lib"),
    ("path = '/tmp/foo'\n", False, "local variable named path"),
]


@pytest.mark.parametrize(
    "source, expect_finding, description",
    _SHIM_EVASIONS,
    ids=[case[2] for case in _SHIM_EVASIONS],
)
def test_shim_scanner_catches_known_evasions(source, expect_finding, description):
    findings = _find_shims(source)
    if expect_finding:
        assert findings, f"expected a finding for {description!r}:\n{source}"
    else:
        assert findings == [], f"unexpected finding(s) for {description!r}: {findings}"


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
