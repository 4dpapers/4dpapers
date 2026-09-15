# Phase 1 — Foundation and Honest Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project an installable package, rebuild the test suite so its numbers mean something, and prove the cross-target fidelity invariant with a harness that demonstrably detects a real colour-scale divergence.

**Architecture:** No module moves, no renames, no new abstractions. Packaging comes first because it is what makes the library importable, which is what lets `conftest.py` exist, which is what lets the hand-rolled importlib shims and skip hatches be deleted. The phase ends with a fidelity harness and the fix it proves.

**Tech Stack:** Python 3.11 (CI) / 3.14 (local venv), pytest, pytest-cov, Playwright, Pillow + numpy, ruff, mypy, Tornado, Quarto, PyVista.

> **Revision note.** This plan was reviewed before execution and five Critical defects were found and corrected: the original `pyproject.toml` installed nothing importable; it mapped only `lib/` when most shims load `4dpaper.py` or modules beside it; it left `lib.`-prefixed internal imports and an unpackaged `scripts/` broken; CI never installed the package; and the scalar-range resolver used all timesteps when the HTML path uses a strided, capped subset — which would have passed the harness on the 8-step example while still diverging on real cases.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-14-backend-restructure-design.md` (Phase 1, section 6; carried-forward items in section 10).
- Every task is one pull request against `main`, reviewed before the next starts.
- **Branch every task explicitly from main:** `git checkout -B <branch> main`. Never from "current HEAD".
- **No module moves, no renames, no new abstractions.** Those are Phase 2 and 3.
- **No new `pytest.skip`.** A test that cannot run in some environment must be made to run, not skipped.
- Tests must run on a fresh checkout and in CI — never dependent on untracked or gitignored data, or on tooling present only on one machine.
- **Offline export must not regress.**
- Local test command: `venv/bin/python -m pytest tests/ -q` from `/Users/simaocastro/4Dpapers`.
- Baseline: **475 passed, 11 skipped, 0 failed** (`pytest tests/`). Bare `pytest` collects 487 because `pytest.ini` also lists `development/quick-export`.
- `main` is clean apart from an untracked `.coverage`.

### Verified facts the tasks depend on

- **13 `spec_from_file_location` shims** across 8 test files. **Nine load `_extensions/4dpaper/4dpaper.py` itself**; the rest load `lib/parser.py`, `lib/frontend.py`, or `export_templates.py`.
- `4dpaper.py` can **never** be imported by name — `fourdpaper.4dpaper` is not a valid identifier. One importlib load is unavoidable; it belongs in `conftest.py`, once.
- Library modules live in **two** places: `_extensions/4dpaper/lib/` (`config, frontend, mesh, parser, render, state, timeseries, utils`) and `_extensions/4dpaper/` itself (`export_templates, shortcut_resolver, cache_bust_assets, inject_figures, sign_rendered_html`).
- `lib/frontend.py:7` uses `from lib.utils import ...` — an internal import that breaks under any rename.
- `scripts/` has **no** `__init__.py`, yet `lib/render.py` imports `scripts.data_loader`.
- `time_global_range` is computed over `_timeline_step_indices(sim, fields, stride)` then `_apply_timeline_frame_budget(...)` — a **strided, capped subset**, not `range(sim.n_steps)`.
- 9 `sys.path` edits in tests; 22 `pytest.skip` + 9 `importorskip` + 4 `skipif`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml` | *(new)* Package metadata; ruff and mypy config | 3 |
| `scripts/__init__.py` | *(new)* Makes `scripts` a package | 3 |
| `tests/conftest.py` | *(new)* Shared fixtures; the **one** place `4dpaper.py` is loaded | 5 |
| `tests/fixtures/niederer.py` | *(new)* Locates and validates the committed example case | 5 |
| `tests/test_fidelity.py` | *(new)* Cross-target fidelity harness | 8 |
| `_extensions/4dpaper/lib/render.py` | Scalar range resolved once for both targets | 9 |
| `.github/workflows/*.yml` | Package install, ruff, mypy, `PLAYWRIGHT_E2E` | 3, 7 |
| `.gitattributes` | *(new)* LFS policy for future fixture data | 7 |

---

### Task 1: Correctness batch

Three small defects from the v0.1.3 whole-release review. `h5py` is deliberately **not** here — it is Task 2, because it may turn a skip into a failure and this PR must go green.

**Files:**
- Modify: `_extensions/4dpaper/export_templates.py`, `dashboard/template_plugin.py`, `dashboard/compile_plugin.py`, `tests/test_compile_plugin.py`
- Test: `tests/test_export_templates.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `apply_template` raises `ValueError` on an unknown template; `_rewrite_paperview_asset_urls_for_pdf` no longer exists.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_export_templates.py` (it already has a `_load()` helper — use it):

```python
def test_unknown_template_name_is_rejected():
    """Silent fallback hides a typo in a published document's styling."""
    mod = _load()
    with pytest.raises(ValueError, match="unknown template"):
        mod.apply_template("<html><head></head><body></body></html>",
                           template="no-such-template")


def test_custom_css_cannot_escape_the_style_block():
    """Exported documents get shared; custom CSS must not inject markup."""
    mod = _load()
    out = mod.apply_template(
        "<html><head></head><body></body></html>",
        template="modern",
        custom_css="body{color:red}</style><script>alert(1)</script>",
    )
    assert "<script>alert(1)</script>" not in out
    assert "</style><script>" not in out
```

- [ ] **Step 2: Run them and confirm both fail**

```bash
venv/bin/python -m pytest tests/test_export_templates.py -v -k "unknown_template or escape_the_style"
```

- [ ] **Step 3: Reject unknown template names**

In `apply_template`, replace `preset_css = TEMPLATES.get(template, TEMPLATES["academic"])` with:

```python
    if template not in TEMPLATES:
        raise ValueError(
            f"unknown template {template!r}; expected one of {sorted(TEMPLATES)}"
        )
    preset_css = TEMPLATES[template]
```

Then read `dashboard/template_plugin.py`, find its own duplicate silent fallback, and make it return HTTP 400 rather than letting the `ValueError` become a 500. Match that file's existing error-response style.

- [ ] **Step 4: Contain custom CSS**

Add to `export_templates.py` and apply at the `custom_css` interpolation point:

```python
def _sanitise_custom_css(css: str) -> str:
    """Prevent custom CSS from closing its <style> block.

    `</style>` inside a style element ends it, so anything after becomes
    live markup in a document that gets shared with reviewers.
    """
    return re.sub(r"</\s*style", r"<\\/style", css, flags=re.IGNORECASE)
```

- [ ] **Step 5: Remove the orphaned function**

```bash
grep -rn "_rewrite_paperview_asset_urls_for_pdf" --include="*.py" . | grep -v venv | grep -v __pycache__
```

Expect matches only in `dashboard/compile_plugin.py` (definition) and `tests/test_compile_plugin.py`. If a production caller exists, STOP and report. Otherwise delete the function and its tests.

- [ ] **Step 6: Full suite, then commit**

```bash
venv/bin/python -m pytest tests/ -q
git checkout -B fix/correctness-batch main
git add _extensions/4dpaper/export_templates.py dashboard/template_plugin.py \
        dashboard/compile_plugin.py tests/test_export_templates.py tests/test_compile_plugin.py
git commit -m "fix: reject unknown templates, contain custom CSS, drop dead code

From the v0.1.3 whole-release review: an unknown template name silently
rendered as 'academic'; custom_css could close its <style> block and
inject markup into a document meant to be shared; and
_rewrite_paperview_asset_urls_for_pdf had no production callers.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin fix/correctness-batch
gh pr create --title "fix: correctness batch from the v0.1.3 review" --body "Three small defects from the whole-release review. See spec section 10.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 2: Add h5py and face what it uncovers

Its own PR because the outcome is genuinely unknown: the skip may be hiding a passing path or a broken one.

**Files:**
- Modify: `requirements.txt`, possibly `scripts/data_loader.py`
- Test: `tests/test_data_loader.py`

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, after `meshio==5.3.5`:

```
# h5py: the generic-HDF5 reader path in scripts/data_loader.py. Without it
# tests/test_data_loader.py skipped, which hid the reader rather than
# testing it.
h5py>=3.10
```

- [ ] **Step 2: Install and run the previously-skipped tests**

```bash
venv/bin/python -m pip install -q "h5py>=3.10"
venv/bin/python -m pytest tests/test_data_loader.py -v -k "hdf5 or h5"
```

- [ ] **Step 3: Act on what you find**

Record the exact output. Then:

- **If they pass:** good — two skips become two tests. Go to Step 4.
- **If one fails:** the skip was hiding a defect. The second skip's message was `Could not deduce file format from path '.../test_data.hdf5'`, which suggests the reader needs an explicit format hint rather than a missing library. Read `SimulationData.load_hdf5` and `_detect_format` in `scripts/data_loader.py` and fix it if the fix is small and local.
- **If the fix is not small:** STOP. Report what is broken and why, and do not re-skip. Leave the failing test failing and ask for guidance — a known failing test is more honest than a skip.

- [ ] **Step 4: Full suite and commit**

```bash
venv/bin/python -m pytest tests/ -q
```

Skip count must drop by at least one.

```bash
git checkout -B fix/h5py-dependency main
git add requirements.txt tests/test_data_loader.py scripts/data_loader.py
git commit -m "fix: add h5py so the HDF5 reader is tested, not skipped

The generic-HDF5 path skipped for a missing library, which hid the
reader rather than reporting on it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin fix/h5py-dependency
gh pr create --title "fix: add h5py dependency" --body "Turns two environment skips into real tests.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 3: Make the project an installable package

The keystone. **The original version of this task was broken in four ways; the corrected form is below. Follow it exactly.**

**Files:**
- Create: `pyproject.toml`, `scripts/__init__.py`
- Modify: `_extensions/4dpaper/4dpaper.py`, `_extensions/4dpaper/lib/frontend.py`, `Dockerfile`, both workflow files
- Test: `tests/test_packaging.py` *(new)*

**Interfaces:**
- Consumes: nothing.
- Produces: `pip install -e .` works; `import fourdpaper.lib.parser`, `import fourdpaper.export_templates`, `import dashboard.*`, `import scripts.data_loader` all succeed with no `sys.path` edits. Tasks 4 and 5 depend on this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packaging.py`:

```python
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
```

- [ ] **Step 2: Run it and confirm it fails**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fourdpaper'`.

- [ ] **Step 3: Write pyproject.toml — explicit packages, not `find`**

`packages.find` will not discover a `package-dir` mapping whose source directory starts with a digit. List packages explicitly:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "fourdpapers"
dynamic = ["version"]
description = "Paper authoring IDE with interactive 3D figures"
requires-python = ">=3.11"

[tool.setuptools.dynamic]
version = { file = "VERSION" }

[tool.setuptools]
# The library lives under a directory whose name starts with a digit, so it
# cannot be imported by its own path. Map it to an importable name rather
# than moving it — module moves belong to Phase 2.
package-dir = { fourdpaper = "_extensions/4dpaper", dashboard = "dashboard", scripts = "scripts" }
packages = ["fourdpaper", "fourdpaper.lib", "dashboard", "scripts"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_unused_ignores = true
```

Note the mapping is `_extensions/4dpaper`, not `.../lib` — modules live in **both** that directory and its `lib/` subdirectory, so both must be reachable.

- [ ] **Step 4: Make `scripts` a package**

```bash
printf '"""Helper scripts, importable so tests need no sys.path edits."""\n' > scripts/__init__.py
```

`_extensions/4dpaper/lib/render.py` already does `import scripts.data_loader`, which only worked because of the `sys.path` injection this task removes.

- [ ] **Step 5: Install and verify each import individually**

```bash
venv/bin/python -m pip install -e . 2>&1 | tail -3
venv/bin/python -c "import fourdpaper; print('pkg  ', fourdpaper.__file__)"
venv/bin/python -c "import fourdpaper.lib.parser as m; print('lib  ', m.__file__)"
venv/bin/python -c "import fourdpaper.export_templates as m; print('ext  ', m.__file__)"
venv/bin/python -c "import scripts.data_loader as m; print('script', m.__file__)"
```

All four must succeed. If any fails, STOP and report which — do not move directories to work around it.

- [ ] **Step 6: Fix the internal `lib.` import**

`_extensions/4dpaper/lib/frontend.py:7` reads `from lib.utils import is_cache_valid`. That resolves only under the old `sys.path` injection. Find every such internal import and rewrite it:

```bash
grep -rn "^from lib\.\|^import lib\.\|[^.]from lib\." _extensions/4dpaper/lib/*.py _extensions/4dpaper/*.py
```

Rewrite each to `from fourdpaper.lib.X import ...`. Re-run Step 5 afterwards.

- [ ] **Step 7: Remove the sys.path surgery and the execv re-launch**

In `_extensions/4dpaper/4dpaper.py`, delete the three `sys.path.insert` calls and the whole `os.execv` re-launch block including its safety check.

The `execv` is already inert — it targets `.venv`, while this project's venv is `venv/` — and `dashboard/utils.py` sets `QUARTO_PYTHON`, falling back to `sys.executable`. Replace the block with nothing, but keep a clear failure mode: if `import fourdpaper` raises, the hook should print an actionable message telling the user to run `pip install -e .`, rather than a bare traceback. Someone running `quarto render` directly, outside the dashboard, will hit this.

Rewrite its `from lib.X import ...` lines to `from fourdpaper.lib.X import ...`.

- [ ] **Step 8: Install the package in CI — both workflows**

This is essential: once Task 4 deletes the `sys.path` edits, tests fail in CI without it. In **both** `.github/workflows/pr-regressions.yml` and `.github/workflows/docker-publish.yml`, in the dependency-install step, add after the `requirements-e2e.txt` install:

```yaml
          python -m pip install -e .
```

- [ ] **Step 9: Install the package in the image**

Read `Dockerfile`, find the `requirements.txt` install, and add an editable install of the project after it, matching the file's style.

- [ ] **Step 10: Verify the Quarto hook still runs**

This is the risk in this task — the hook runs as a Quarto subprocess, not under pytest.

```bash
venv/bin/python -m pytest tests/test_export_pipeline.py -v
```

These shell out to real `quarto render`, exercising the hook as Quarto invokes it. If they fail, the import rewiring is wrong. Fix before continuing.

- [ ] **Step 11: Full suite and commit**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
venv/bin/python -m pytest tests/ -q
git checkout -B feat/installable-package main
git add pyproject.toml scripts/__init__.py _extensions/4dpaper/4dpaper.py \
        _extensions/4dpaper/lib/frontend.py tests/test_packaging.py Dockerfile .github/workflows/
git commit -m "feat: make the project an installable package

The library could not be imported, because its directory starts with a
digit and the project had no package metadata. That forced three
sys.path injections, an os.execv re-launch, and thirteen importlib
shims across the test suite.

Maps both _extensions/4dpaper and its lib/ subdirectory to an importable
name without moving anything; module moves belong to Phase 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin feat/installable-package
gh pr create --title "feat: installable package" --body "Keystone of Phase 1: makes the library importable, which is what lets the test suite be rebuilt.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 4: Delete the shims and sys.path edits

**Files:**
- Create: `tests/conftest.py` (the `fourdpaper_hook` fixture only; the rest arrives in Task 5)
- Modify: `tests/test_camera_lock.py`, `test_controls_strip.py`, `test_export_templates.py`, `test_extension.py`, `test_graph_camera.py`, `test_panel_sync.py`, `test_styles.py`, `test_timeseries.py`

**Interfaces:**
- Consumes: the package from Task 3.
- Produces: zero `spec_from_file_location` in `tests/test_*.py`; one deliberate load in `conftest.py`; zero `sys.path` in `tests/`.

- [ ] **Step 1: Inventory what must go**

```bash
grep -rn "spec_from_file_location" tests/*.py
grep -rn "sys.path" tests/*.py
```

Expected: 13 and 9. Note which load `4dpaper.py` (nine of them) versus a library module.

- [ ] **Step 2: Add the one legitimate loader to conftest**

`4dpaper.py` is a script, not a module — `fourdpaper.4dpaper` is not a valid identifier, so it can never be imported by name. One importlib load is unavoidable. It belongs in one place.

Create `tests/conftest.py`:

```python
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
```

- [ ] **Step 3: Write the guards**

Add to `tests/test_packaging.py`:

```python
import pathlib


def test_no_importlib_shims_in_test_modules():
    """Shims regenerate quietly — v0.1.3 added two while the cause was unfixed.

    conftest.py is exempt: it holds the single unavoidable load of
    4dpaper.py, which is a script and cannot be imported by name.
    """
    offenders = [
        str(p) for p in pathlib.Path("tests").rglob("test_*.py")
        if "spec_from_file_location" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, f"importlib shims remain in: {offenders}"


def test_no_sys_path_manipulation_in_tests():
    offenders = [
        str(p) for p in pathlib.Path("tests").rglob("*.py")
        if "sys.path" in p.read_text(encoding="utf-8")
        and p.name != "conftest.py"
    ]
    assert not offenders, f"sys.path edits remain in: {offenders}"
```

- [ ] **Step 4: Run the guards and confirm they fail**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v -k "shims or sys_path"
```

Expected: both FAIL, listing the 8 files.

- [ ] **Step 5: Convert one file at a time**

For each file from Step 1:

- A shim loading a **library module** becomes a normal import, e.g. `from fourdpaper.lib import parser`, and `_load_parser().parse_graph_shortcodes(...)` becomes `parser.parse_graph_shortcodes(...)`.
- A shim loading **`4dpaper.py`** becomes the `fourdpaper_hook` fixture: add `fourdpaper_hook` to the test's parameters and replace `_load_4dpaper()` with it. Where the shim is used at module scope rather than inside a test, move the usage into the test body.

Run that file's tests after each conversion:

```bash
venv/bin/python -m pytest tests/<file> -q
```

Do not move on until it passes. If a module cannot be imported by name, STOP and report — Task 3's mapping is incomplete.

- [ ] **Step 6: Confirm guards pass, then the full suite**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
venv/bin/python -m pytest tests/ -q
```

The pass count must not DROP. A drop means a shim was deleted along with the tests using it.

- [ ] **Step 7: Commit**

```bash
git checkout -B refactor/delete-test-shims main
git add tests/
git commit -m "refactor: import modules directly in tests

Deletes 13 spec_from_file_location shims across 8 files and 9 sys.path
edits, all of which existed only because the package was not importable.

One load survives, in conftest.py: 4dpaper.py is a script whose module
name is not a valid identifier, so it can never be imported by name.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin refactor/delete-test-shims
gh pr create --title "refactor: delete test importlib shims" --body "13 shims and 9 sys.path edits removed, with guards against regrowth.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 5: Real fixtures and the five dead tests

Five tests in `tests/test_extension.py` (lines 651, 686, 725, 749, 781) gate on `/data/tutorials/NiedererEtAl2012/Niederer.foam` — an absolute path present on no machine, in no CI run, and in no image. They report as "skipped", which reads as conditional. They are unreachable. The correct fixture, `examples/niederer/data/niederer/` (8 timesteps, 5 fields, 3.2 MB), is committed.

**Files:**
- Create: `tests/fixtures/__init__.py`, `tests/fixtures/niederer.py`
- Modify: `tests/conftest.py`, `tests/test_extension.py`

**Interfaces:**
- Consumes: Task 4's `conftest.py`.
- Produces: `niederer_case`, `niederer_sim`, `project_root` fixtures. Task 8's harness depends on `niederer_case`.

- [ ] **Step 1: Write the fixture locator**

Create `tests/fixtures/__init__.py` (empty) and `tests/fixtures/niederer.py`:

```python
"""Locators for the committed example case.

A real, redistributable 8-timestep VTK series under examples/niederer/.
Tests point here, never at an absolute path on one developer's machine.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
NIEDERER_DIR = REPO_ROOT / "examples" / "niederer" / "data" / "niederer"
NIEDERER_SERIES = NIEDERER_DIR / "niederer.vtk.series"

EXPECTED_STEPS = 8
EXPECTED_FIELDS = {"Jsi", "Vm", "activationTime", "externalStimulusCurrent", "ionicCurrent"}


def assert_case_present() -> Path:
    """Fail loudly if the committed fixture is missing.

    A missing fixture must fail, never skip — skipping is what let five
    tests sit unreachable for months.
    """
    if not NIEDERER_SERIES.is_file():
        raise AssertionError(
            f"committed example case missing at {NIEDERER_SERIES}; "
            "it is tracked in git, so check out the full repository"
        )
    return NIEDERER_SERIES
```

- [ ] **Step 2: Extend conftest**

Append to `tests/conftest.py`:

```python
from tests.fixtures.niederer import assert_case_present


@pytest.fixture(scope="session")
def project_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def niederer_case() -> Path:
    """The committed example .vtk.series. Fails if absent."""
    return assert_case_present()


@pytest.fixture(scope="session")
def niederer_sim(niederer_case):
    from scripts.data_loader import SimulationData
    return SimulationData(str(niederer_case)).load()
```

`tests/__init__.py` already exists, so `from tests.fixtures...` resolves.

- [ ] **Step 3: Prove the fixture is real before repointing anything at it**

Add to `tests/test_packaging.py`:

```python
def test_committed_example_case_loads(niederer_sim):
    from tests.fixtures.niederer import EXPECTED_FIELDS, EXPECTED_STEPS
    assert niederer_sim.n_steps == EXPECTED_STEPS
    assert EXPECTED_FIELDS.issubset(set(niederer_sim.fields))
```

```bash
venv/bin/python -m pytest tests/test_packaging.py -v -k example_case
```

Expected: PASS.

- [ ] **Step 4: Repoint the five dead tests**

In `tests/test_extension.py`, replace each of the five occurrences of:

```python
        case_path = Path("/data/tutorials/NiedererEtAl2012/Niederer.foam")
        if not case_path.exists():
            pytest.skip("Niederer case not available")
```

with use of the `niederer_case` fixture. Delete the `pytest.skip`.

These were written against an OpenFOAM `.foam` case and will now run against a `.vtk.series`. **Expect failures** on assumptions specific to the old case — field names, timestep counts, `part=` arguments. That is the point: they have never run. For each failure, decide and record:

- assertion genuinely wrong for this fixture → correct it;
- test meaningless without an OpenFOAM case → **delete it**, with reasoning.

Do not reintroduce a skip.

- [ ] **Step 5: Run and record**

```bash
venv/bin/python -m pytest tests/test_extension.py -v
venv/bin/python -m pytest tests/ -q
```

Skip count drops by 5. Record which of the five now pass, which were adjusted, and which were deleted.

- [ ] **Step 6: Commit**

```bash
git checkout -B test/real-fixtures main
git add tests/
git commit -m "test: point the dead tests at the committed fixture

Five tests gated on an absolute path present on no machine and in no CI
run. They reported as skipped, which reads as conditional; they were
unreachable. A missing fixture now fails rather than skipping.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/real-fixtures
gh pr create --title "test: real fixtures for the dead tests" --body "Makes five unreachable tests run against the committed example case.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 6: Enumerate every remaining skip

**Files:**
- Create: `tests/test_no_silent_skips.py`
- Modify: whichever files still hold hatches

- [ ] **Step 1: Enumerate**

```bash
venv/bin/python -m pytest tests/ -q -rs 2>&1 | grep "^SKIPPED"
grep -rn "pytest.skip\|importorskip\|skipif" tests/ development/quick-export --include="*.py"
```

- [ ] **Step 2: Write the enforcement test**

Create `tests/test_no_silent_skips.py`:

```python
"""Every skip must be deliberate and enumerated.

The suite once reported 11 skips, of which 5 were unreachable tests and
2 were environment accidents. A skip nobody enumerated is a test nobody
knows is missing.

Covers both roots in pytest.ini: tests/ and development/quick-export.
"""
from __future__ import annotations

import pathlib
import re

ALLOWED_SKIPS = {
    ("tests/e2e/test_dashboard_split.py", "browser E2E, gated on PLAYWRIGHT_E2E"),
    ("tests/e2e/test_quick_export.py", "needs a running Quick Export server"),
}

SKIP_RE = re.compile(r"pytest\.skip|importorskip|mark\.skipif")
ROOTS = ("tests", "development/quick-export")


def test_only_allowed_files_contain_skips():
    allowed = {f for f, _ in ALLOWED_SKIPS}
    offenders = []
    for root in ROOTS:
        for p in sorted(pathlib.Path(root).rglob("test_*.py")):
            rel = p.as_posix()
            if rel in allowed:
                continue
            if SKIP_RE.search(p.read_text(encoding="utf-8")):
                offenders.append(rel)
    assert not offenders, (
        "skips outside the allowlist: " + ", ".join(offenders) +
        " — make the test run, delete it, or justify it in ALLOWED_SKIPS"
    )
```

- [ ] **Step 3: Run it to get the real list**

```bash
venv/bin/python -m pytest tests/test_no_silent_skips.py -v
```

Expected: FAIL, naming every file still holding a skip.

- [ ] **Step 4: Resolve each offender**

Per file, choose one and record it: **make it run** (preferred), **delete it**, or **allowlist it** with a one-line reason. The `.foam` skip in `tests/test_render_case_preview.py` cites CLAUDE.md §6.0 — either repoint it at `niederer_case` if it needs no OpenFOAM specifics, or allowlist it with that reason.

- [ ] **Step 5: Confirm and commit**

```bash
venv/bin/python -m pytest tests/test_no_silent_skips.py -v
venv/bin/python -m pytest tests/ -q -rs 2>&1 | tail -6
git checkout -B test/no-silent-skips main
git add tests/ development/quick-export
git commit -m "test: enumerate every skip, resolve the rest

A skip nobody enumerated is a test nobody knows is missing.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/no-silent-skips
gh pr create --title "test: enumerate every skip" --body "Resolves remaining hatches and gates new ones behind an allowlist.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 7: CI gates and the data policy

**Files:**
- Create: `.gitattributes`
- Modify: both workflow files, `requirements-e2e.txt`

- [ ] **Step 1: Measure the lint burden before committing to a rule set**

```bash
venv/bin/python -m pip install -q ruff mypy
venv/bin/python -m ruff check . 2>&1 | tail -5
venv/bin/python -m ruff check . --statistics 2>&1 | head -20
```

If ruff reports more than roughly 50 findings, do NOT fix them all — that buries the gate in churn this phase forbids. Narrow `select` in `pyproject.toml` to what passes cleanly plus `F` (real errors), record the deferred rules in your report, and widen later.

- [ ] **Step 2: Fix what the chosen set reports**

```bash
venv/bin/python -m ruff check --fix .
git diff --stat
venv/bin/python -m ruff check .
```

Review the auto-fixes before accepting. Do not blind-commit formatting changes to files this phase should not touch.

- [ ] **Step 3: Scope mypy to something enforceable now**

```bash
venv/bin/python -m mypy dashboard 2>&1 | tail -10
```

Start with `dashboard/` only, `ignore_missing_imports = true`, no strictness flags. Record the scope and why.

- [ ] **Step 4: Add the gates to both workflows**

In **both** `pr-regressions.yml` and `docker-publish.yml` (the `verify` job), after dependency install:

```yaml
      - name: Lint and type-check
        run: |
          python -m pip install ruff mypy
          python -m ruff check .
          python -m mypy dashboard

      - name: Install Playwright browsers
        run: python -m playwright install --with-deps chromium
```

and add `PLAYWRIGHT_E2E: "1"` to the test step's `env:` block alongside `PYVISTA_OFF_SCREEN`.

The two workflows were brought to parity in v0.1.3 — keep them that way, and diff their steps to confirm.

- [ ] **Step 5: Confirm E2E actually runs**

```bash
PLAYWRIGHT_E2E=1 venv/bin/python -m pytest tests/e2e/test_dashboard_split.py -v 2>&1 | tail -10
```

If it fails for a real reason, that is a genuine finding — report it rather than reverting the gate.

- [ ] **Step 6: Add the LFS policy**

Create `.gitattributes`:

```
# Simulation fixtures can be large. Anything matching these patterns is
# stored via Git LFS so the repository stays clonable. Current fixtures
# (3.2 MB niederer, 5.5 MB tests/data) are small enough not to need it —
# this exists so the next example case lands correctly rather than
# bloating history, which cannot be undone on a published repo.
*.vtu   filter=lfs diff=lfs merge=lfs -text
*.vtp   filter=lfs diff=lfs merge=lfs -text
*.vtk   filter=lfs diff=lfs merge=lfs -text
*.exo   filter=lfs diff=lfs merge=lfs -text
*.cgns  filter=lfs diff=lfs merge=lfs -text
*.h5    filter=lfs diff=lfs merge=lfs -text
*.hdf5  filter=lfs diff=lfs merge=lfs -text
```

**Do NOT run `git lfs migrate`** — rewriting a published repository's history breaks every existing clone. Confirm existing files are untouched:

```bash
git status --porcelain
```

Expected: only `.gitattributes` as new. If tracked files show as modified, STOP and report.

- [ ] **Step 7: Commit**

```bash
venv/bin/python -m pytest tests/ -q
git checkout -B ci/lint-and-e2e-gates main
git add .gitattributes .github/workflows/ pyproject.toml requirements-e2e.txt
git commit -m "ci: enforce ruff, mypy and browser E2E on both gates

The browser tests were the only layer that could catch a dead figure,
and they were disabled everywhere — which is how the viewer_logic.js
regression shipped.

Adds an LFS policy for future fixture data; existing history is left
alone deliberately.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin ci/lint-and-e2e-gates
gh pr create --title "ci: lint, type and browser E2E gates" --body "Enables ruff, mypy and PLAYWRIGHT_E2E on the PR gate and the release gate, plus the LFS policy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 8: The cross-target fidelity harness

The heart of the phase. **This PR is expected to be red** — a harness that passes on first run has not been shown to detect anything.

**Files:**
- Create: `tests/test_fidelity.py`
- Modify: `requirements-e2e.txt` (Pillow)

**Interfaces:**
- Consumes: `niederer_case` (Task 5); `fourdpaper.lib.render` (Task 3).
- Produces: `warm_fraction()` and the `render_pair` fixture, used by Task 9 to prove the fix.

**Detection method, validated in advance.** A strict pixel comparison cannot work — vtk.js and offscreen VTK differ in antialiasing and lighting. The *warm-pixel fraction* of the mesh region does: measured on the existing `niederer-slab` pair, **HTML 5.0% against PNG 20.1%**, a gap caused purely by the colour-scale divergence and far outside rendering noise.

Two controls matter, both learned from review: **turn the colorbar off**, because it puts a full coolwarm gradient into both images at different pixel shares; and **pin the camera**, because the two paths otherwise apply different defaults. Without these, the post-fix residual is systematic rather than noise.

- [ ] **Step 1: Add Pillow**

Add `Pillow>=10.0` to `requirements-e2e.txt`, then `venv/bin/python -m pip install -q "Pillow>=10.0"`.

- [ ] **Step 2: Read the real signatures before writing the fixture**

```bash
venv/bin/python -c "
import inspect
from fourdpaper.lib.render import generate_html_figure, generate_png_figure
print('PNG :', inspect.signature(generate_png_figure))
print('HTML:', inspect.signature(generate_html_figure))
"
```

Match the fixture's keyword arguments to what you see. Do not assume the two signatures agree.

- [ ] **Step 3: Write the harness**

Create `tests/test_fidelity.py`:

```python
"""Cross-target fidelity: a figure must read the same in HTML and in PDF.

The HTML path scales scalars across the timesteps it embeds, while the
PNG path that feeds PDF export lets PyVista auto-scale to a single
timestep. Same data, same timestep, different colours.

Pixel-exact comparison cannot work — vtk.js and offscreen VTK differ in
antialiasing and lighting. Warm-pixel fraction does: measured 5.0%
against 20.1% on the committed example, far outside rendering noise.

The colorbar is disabled and the camera pinned so the only thing that
can move the measurement is the colour scale itself.
"""
from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest
from PIL import Image

FIELD = "activationTime"
TIME_SPEC = "mid"
FIG_ID = "fidelity-probe"
WARM_FRACTION_TOLERANCE = 0.05

PINNED_CAMERA = {
    "position": [0.12, -0.09, 0.08],
    "focal_point": [0.0, 0.0, 0.01],
    "view_up": [0.0, 0.0, 1.0],
}


def warm_fraction(path: pathlib.Path, crop_top_fraction: float = 0.0) -> float:
    """Share of non-background pixels that are red-dominant.

    Reflects where values sit in the colourmap, so a change of scalar
    range moves it sharply while antialiasing does not.
    """
    arr = np.asarray(Image.open(path).convert("RGB")).astype(float)
    if crop_top_fraction:
        arr = arr[int(arr.shape[0] * crop_top_fraction):, :]
    mask = arr.sum(axis=2) < 700
    px = arr[mask]
    assert len(px) > 500, f"{path.name}: only {len(px)} mesh pixels — did it render?"
    return float((px[:, 0] > px[:, 2] + 20).mean())


@pytest.fixture(scope="module")
def render_pair(niederer_case, project_root, tmp_path_factory):
    from playwright.sync_api import sync_playwright

    from fourdpaper.lib.render import generate_html_figure, generate_png_figure

    # Pin the camera so both paths start from the same viewpoint.
    state_dir = project_root / "state"
    state_dir.mkdir(exist_ok=True)
    cam_file = state_dir / f"camera_{FIG_ID}.json"
    cam_file.write_text(json.dumps(PINNED_CAMERA), encoding="utf-8")

    out = tmp_path_factory.mktemp("fidelity")
    html_path, png_path, shot_path = out / "fig.html", out / "fig.png", out / "shot.png"

    common = dict(
        src_path=niederer_case, field=FIELD, time_spec=TIME_SPEC, fig_id=FIG_ID,
        background="white", axis_color="black", cmap="coolwarm",
        show_colorbar=False, decimate="none",
    )
    try:
        generate_png_figure(output_path=png_path, **common)
        generate_html_figure(
            output_path=html_path, available_fields=[FIELD],
            show_lock_btn=False, show_orientation=False, **common
        )

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 900, "height": 600})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(html_path.resolve().as_uri())
            page.wait_for_timeout(6000)
            page.screenshot(path=str(shot_path))
            browser.close()
        assert not errors, f"figure raised JS errors: {errors[:2]}"
        yield {"html": html_path, "png": png_path, "shot": shot_path}
    finally:
        cam_file.unlink(missing_ok=True)


def test_html_figure_actually_renders(render_pair):
    """Guards the guard: a blank canvas must not silently pass the comparison."""
    assert render_pair["shot"].stat().st_size > 5000
    warm_fraction(render_pair["shot"], crop_top_fraction=0.06)  # asserts pixel count


def test_html_and_pdf_agree_on_colour_scale(render_pair):
    """The core invariant: the same figure must read the same in both targets."""
    html_warm = warm_fraction(render_pair["shot"], crop_top_fraction=0.06)
    png_warm = warm_fraction(render_pair["png"])
    assert abs(html_warm - png_warm) <= WARM_FRACTION_TOLERANCE, (
        f"HTML and PDF disagree on colour scale: HTML warm={html_warm:.3f}, "
        f"PNG warm={png_warm:.3f}, difference {abs(html_warm - png_warm):.3f} "
        f"exceeds {WARM_FRACTION_TOLERANCE}"
    )
```

Adjust `PINNED_CAMERA` if the figure renders off-frame — check the screenshot and choose values that frame the mesh. Record what you used.

- [ ] **Step 4: Run it and confirm it FAILS**

```bash
venv/bin/python -m pytest tests/test_fidelity.py -v
```

**Expected: `test_html_and_pdf_agree_on_colour_scale` FAILS** with a difference above 0.05. Record the exact numbers — they are the evidence the harness detects the defect.

If it PASSES, the harness is not measuring what it must. Do not proceed. Check that the screenshot is not blank, that `FIELD` is the one embedded, and that both calls received the same `time_spec`.

- [ ] **Step 5: Commit the deliberately red PR**

```bash
git checkout -B test/fidelity-harness main
git add tests/test_fidelity.py requirements-e2e.txt
git commit -m "test: add the cross-target fidelity harness

Asserts a figure reads the same in HTML and in the PNG that feeds PDF
export. It fails today, which is the point: the HTML path scales
scalars across the timesteps it embeds while the PNG path scales to
one, so activationTime renders pale blue in HTML and red in PDF.

Compares warm-pixel fraction rather than pixels, with the colorbar off
and the camera pinned so only the colour scale can move the result.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/fidelity-harness
gh pr create --title "test: cross-target fidelity harness (expected red)" --body "**This PR is expected to fail CI.** The harness detects a real divergence that the next PR fixes.

A harness that passes on first run has not been shown to detect anything.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 6: Report the numbers**

Record the HTML and PNG warm fractions and their difference. Task 9 is judged against them.

---

### Task 9: Fix the colour-scale divergence

**Files:**
- Modify: `_extensions/4dpaper/lib/render.py`, `tests/test_fidelity.py` (tolerance only)

**Interfaces:**
- Consumes: the harness from Task 8.
- Produces: both render paths resolve scalar range identically, over the same steps.

**The subtlety that matters.** `generate_html_figure` computes `time_global_range` only when `embed_timeline and sim.n_steps > 1 and fields_to_embed`, and over `_timeline_step_indices(sim, fields, stride)` further reduced by `_apply_timeline_frame_budget(...)` — a **strided, capped subset**. A resolver over `range(sim.n_steps)` would match it only on the 8-step example and diverge again on real cases, passing the harness while shipping the bug. The PNG path must use *the same indices the HTML path embedded*.

- [ ] **Step 1: Read both paths**

```bash
sed -n '740,790p' _extensions/4dpaper/lib/render.py   # HTML: how step_indices is derived
grep -n "_add_mesh_auto" _extensions/4dpaper/lib/render.py
```

Line ~633 is in `generate_png_figure`; ~703 in `generate_html_figure`. Neither passes `clim`.

- [ ] **Step 2: Add one resolver, taking explicit steps**

Add to `_extensions/4dpaper/lib/render.py` after the imports:

```python
def _resolve_scalar_range(sim, field: str, step_indices):
    """Scalar range for a field over exactly the given steps.

    Both render targets must ask the same question over the same steps
    and get the same answer. When they resolved range independently the
    HTML path scaled across the timesteps it embedded and the PNG path
    scaled to one, so identical values mapped to different colours.

    `step_indices` is required, not optional: the HTML path embeds a
    strided, budget-capped subset, and matching it is the whole point.

    Returns None when the field is absent or has no finite values, so the
    caller falls back to PyVista's own behaviour.
    """
    import numpy as _np

    if not field or not step_indices:
        return None
    lo, hi = float("inf"), float("-inf")
    for i in step_indices:
        mesh = sim.get_mesh(i)
        if mesh is None:
            continue
        arr = mesh.point_data.get(field)
        if arr is None:
            arr = mesh.cell_data.get(field)
        if arr is None or len(arr) == 0:
            continue
        finite = _np.asarray(arr)[_np.isfinite(arr)]
        if finite.size == 0:
            continue
        lo = min(lo, float(finite.min()))
        hi = max(hi, float(finite.max()))
    if lo == float("inf") or hi <= lo:
        return None
    return [lo, hi]
```

- [ ] **Step 3: Use it in the HTML path, replacing the inline computation**

Find where `time_global_range[f]` is assigned from the `_tg_min`/`_tg_max` accumulators and replace that computation with `_resolve_scalar_range(sim, f, step_indices)`, so there is exactly one implementation. Keep the existing `[0.0, 1.0]` fallback behaviour when it returns `None`.

Then pass the active field's range as `clim` to the HTML path's `_add_mesh_auto` call, so the static first paint matches the animated frames.

- [ ] **Step 4: Use the same steps in the PNG path**

`generate_png_figure` does not embed a timeline, so it must reconstruct the same indices. Extract the derivation from `generate_html_figure` into a small helper both call — for example `_embedded_step_indices(sim, fields, stride, surface)` returning the post-budget list — and use it in both. Read the HTML path carefully: the budget depends on the decimated surface's point count, so the helper needs that argument.

If `generate_png_figure` cannot reach the same inputs (for example it lacks `stride`), STOP and report rather than guessing. Falling back to all steps would silently reintroduce the divergence.

- [ ] **Step 5: Run the harness — it must now pass**

```bash
venv/bin/python -m pytest tests/test_fidelity.py -v
```

Record the new warm fractions beside Task 8's.

- [ ] **Step 6: Tighten the tolerance to the measured residual**

With the colorbar off and the camera pinned, the post-fix difference should be small. Replace the placeholder `0.05` with a value just above what you actually measured — for example if the residual is 0.004, set `0.02`. A tolerance far looser than the real residual would let a future regression through. Record the measured residual and the chosen tolerance.

- [ ] **Step 7: Check nothing else moved**

```bash
venv/bin/python -m pytest tests/ -q
```

Figure tests asserting on generated output may legitimately change, since colours now differ. For each, confirm the NEW behaviour is correct before updating the assertion, and say so.

- [ ] **Step 8: Commit**

```bash
git checkout -B fix/shared-scalar-range main
git add _extensions/4dpaper/lib/render.py tests/test_fidelity.py
git commit -m "fix: resolve scalar range once, over the same steps

The HTML path scaled scalars across the timesteps it embedded while the
PNG path that feeds PDF export let PyVista auto-scale to one, so
identical values mapped to different colours. On the committed example
activationTime rendered at 62.3% of the HTML span — pale blue in HTML,
bright red in the PDF.

Both paths now use one resolver over the same strided, budget-capped
step list, so they cannot disagree.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin fix/shared-scalar-range
gh pr create --title "fix: shared scalar range across render targets" --body "Makes the fidelity harness pass. Both paths resolve range through one function over identical steps.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 10: Remove the unused file-sync endpoint

Decided by the project owner: live file sync shipped in 0.1.3 with no client — no `/api/sync` or WebSocket code exists anywhere in `dashboard/static/`. It is an authenticated socket that broadcasts file contents plus a recursive watcher, with nothing consuming it. Remove the live surface; keep the work in history.

**Files:**
- Delete: `dashboard/sync_plugin.py`, `tests/test_sync_plugin.py`
- Modify: `dashboard/plugins.py`, `serve.py`, `requirements.txt`

- [ ] **Step 1: Confirm there is genuinely no consumer**

```bash
grep -rniE "api/sync|new WebSocket|file_modified" dashboard/static/ --include="*.js" --include="*.html" | grep -v vendor
```

Expected: no output. **If anything appears, STOP** — a client exists and this task is wrong.

- [ ] **Step 2: Remove the wiring**

- `dashboard/plugins.py`: drop the `sync_plugin` import and its entry in `ROUTES`.
- `serve.py`: drop the `start_observer` import and call.
- `requirements.txt`: remove `watchdog>=4.0.0` and its comment — but first confirm nothing else uses it:

```bash
grep -rn "watchdog" --include="*.py" . | grep -v venv | grep -v __pycache__
```

- [ ] **Step 3: Delete the module and its tests**

```bash
git rm dashboard/sync_plugin.py tests/test_sync_plugin.py
```

The code remains in history at tag `v0.1.3`, so re-adding it later is a revert, not a rewrite.

- [ ] **Step 4: Prove the route is gone**

Add to `tests/test_dashboard_security.py` (read it first and match its style):

```python
def test_no_unused_sync_websocket_route():
    """The file-sync socket shipped with no client, so it is not served.

    It broadcast full file contents; carrying that surface for a feature
    nothing consumed was not worth it. History keeps the code at v0.1.3.
    """
    from dashboard.plugins import ROUTES
    assert not any("/api/sync" in str(r[0]) for r in ROUTES)
```

- [ ] **Step 5: Verify the server still starts**

```bash
venv/bin/python -c "import serve; import dashboard.plugins as p; print('routes:', len(p.ROUTES))"
venv/bin/python -m pytest tests/ -q
```

Expected: imports cleanly; suite passes with 6 fewer tests (the deleted sync tests) and no failures.

- [ ] **Step 6: Commit**

```bash
git checkout -B chore/remove-unused-sync main
git add -u && git add tests/test_dashboard_security.py
git commit -m "chore: remove the unused file-sync endpoint

Shipped in 0.1.3 with no client — no /api/sync or WebSocket code exists
in dashboard/static. An authenticated socket broadcasting file contents,
plus a recursive watcher on the project root, for a feature nothing
consumed.

The code stays in history at v0.1.3, so restoring it is a revert.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin chore/remove-unused-sync
gh pr create --title "chore: remove the unused file-sync endpoint" --body "Removes live attack surface for a feature with no consumer. Code remains at v0.1.3.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 11: Close the phase

- [ ] **Step 1: Verify from a clean tree**

```bash
git checkout main && git pull
git status --porcelain   # .coverage is untracked scratch and may appear
venv/bin/python -m pytest tests/ -q -rs 2>&1 | tail -8
```

Expected: zero failures; every remaining skip in `ALLOWED_SKIPS`.

- [ ] **Step 2: Record the phase's numbers**

```bash
venv/bin/python -m pytest tests/ -q \
  --cov=dashboard --cov=scripts --cov=_extensions/4dpaper --cov-report=term | tail -3
grep -rl "spec_from_file_location" tests/test_*.py | wc -l
```

Expected: zero test modules with shims. Compare coverage against the 51% that closed Phase 0.

- [ ] **Step 3: Update VERSION and CHANGELOG**

Bump `VERSION` to the next patch number. Add a CHANGELOG entry covering the installable package, the deleted shims and skips, the CI gates, the removed sync endpoint, and the colour-scale fix. Match the existing style.

State the colour-scale fix in user terms: figures in exported PDFs previously used a different colour scale from the same figure in HTML.

- [ ] **Step 4: Update the spec**

In `docs/superpowers/specs/2026-09-14-backend-restructure-design.md`, mark Phase 1 shipped with its version, as Phase 0 is marked.

Then **explicitly schedule or defer** these section 10 items, which are silently-wrong-output risks that no task in this phase addressed:

- `apply_template` is HTML-only and never applied to PDF — a direct breach of the section 2 invariant.
- `_validate_native_pdf_output` cannot detect a PDF that rendered without its figures.
- `?v=` cache-busting defeats pandoc's `embed-resources` for the standalone HTML export.
- Export templates never emit `@font-face`, so all four fall back everywhere.

For each, write one line saying which phase owns it. Do not leave them unassigned — that is how they were missed the first time.

- [ ] **Step 5: Commit and tag**

```bash
git add VERSION CHANGELOG.md docs/superpowers/specs/
git commit -m "chore: close Phase 1

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push
git tag "v$(cat VERSION)"
git push origin "v$(cat VERSION)"
gh run watch
```

---

## Definition of done

- `pip install -e .` works; `fourdpaper.lib.*`, `fourdpaper.export_templates`, `dashboard.*` and `scripts.*` all import with no `sys.path` edits, in a fresh interpreter, in CI, and in the image.
- Zero `spec_from_file_location` in `tests/test_*.py`; exactly one deliberate load in `conftest.py`, documented.
- Every remaining skip enumerated in `ALLOWED_SKIPS` with a reason.
- The five previously-unreachable tests run, or are deleted with recorded reasoning.
- ruff, mypy and `PLAYWRIGHT_E2E=1` enforced on the PR gate and the release gate.
- `tests/test_fidelity.py` passes, with its pre-fix failure recorded as evidence it detects the defect, and a tolerance set from the measured residual.
- The unused sync endpoint is gone.
- Every section 10 item is assigned to a phase.
- Working tree clean; phase tagged.

## Next

Phase 2 — `readers/`, `publish/`, `server/`. It depends on this phase's fidelity harness, which is what makes restructuring the render pipeline in Phase 3 survivable.
