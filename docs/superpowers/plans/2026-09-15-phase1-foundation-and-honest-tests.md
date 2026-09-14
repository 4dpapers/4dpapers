# Phase 1 — Foundation and Honest Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the project an installable package, rebuild the test suite so its results mean something, and prove the cross-target fidelity invariant with a harness that demonstrably detects a real divergence.

**Architecture:** No module moves, no renames, no new abstractions. Packaging comes first because it is what makes `4dpaper.py` importable, which is what lets `conftest.py` exist, which is what lets 13 hand-rolled importlib shims and 35 skip hatches be deleted. The phase ends with a fidelity harness and the `clim` fix it proves.

**Tech Stack:** Python 3.11 (CI) / 3.14 (local venv), pytest, pytest-cov, Playwright, Pillow + numpy, ruff, mypy, Tornado, Quarto, PyVista.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-09-14-backend-restructure-design.md` (Phase 1, section 6).
- Every task is one pull request against `main`, reviewed before the next starts.
- **Branch every task explicitly from main:** `git checkout -B <branch> main`. Never from "current HEAD".
- **No module moves, renames, or new abstractions.** Those are Phase 2 and 3. This phase changes packaging, tests, and one behaviour fix.
- **No new `pytest.skip` may be introduced.** A test that cannot run in some environment must be made to run, not skipped.
- Tests must run on a fresh checkout and in CI — never dependent on untracked or gitignored data, or on tooling present only on one developer's machine.
- **Offline export must not regress.** Nothing may reintroduce a remote subresource.
- Local test command: `venv/bin/python -m pytest tests/ -q` from `/Users/simaocastro/4Dpapers`.
- Baseline at plan time: **475 passed, 11 skipped, 0 failed** (`pytest tests/`). Bare `pytest` collects 487 because `pytest.ini` also lists `development/quick-export`.
- Current state to be eliminated: **13** `spec_from_file_location` shims across 8 test files, **9** `sys.path` edits in tests, **22** `pytest.skip` + **9** `importorskip` + **4** `skipif`.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `pyproject.toml` | *(new)* Package metadata, tool config for ruff and mypy | 2 |
| `tests/conftest.py` | *(new)* Shared fixtures; the single place modules under test are loaded | 4 |
| `tests/fixtures/niederer.py` | *(new)* Locates and validates the committed example case | 4 |
| `tests/test_fidelity.py` | *(new)* Cross-target fidelity harness | 7 |
| `_extensions/4dpaper/lib/render.py` | `clim` resolution shared by both render paths | 8 |
| `.github/workflows/*.yml` | ruff, mypy, `PLAYWRIGHT_E2E` gates | 6 |
| `.gitattributes` | *(new)* LFS policy for future fixture data | 6 |
| `requirements.txt` | `h5py`; dev extras | 1, 6 |

---

### Task 1: Correctness batch

Four small defects from the v0.1.3 whole-release review (spec section 10). Grouped because each is a few lines and none needs its own review cycle.

**Files:**
- Modify: `requirements.txt`, `_extensions/4dpaper/export_templates.py`, `dashboard/template_plugin.py`, `dashboard/compile_plugin.py`, `tests/test_compile_plugin.py`
- Test: `tests/test_export_templates.py`, `tests/test_data_loader.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `apply_template` raises `ValueError` on an unknown template name; `_rewrite_paperview_asset_urls_for_pdf` no longer exists.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_export_templates.py`:

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

- [ ] **Step 2: Run them and confirm they fail**

```bash
venv/bin/python -m pytest tests/test_export_templates.py -v -k "unknown_template or escape_the_style"
```

Expected: both FAIL — `apply_template` currently falls back to `academic` silently and injects `custom_css` verbatim.

- [ ] **Step 3: Reject unknown template names**

In `_extensions/4dpaper/export_templates.py`, in `apply_template`, replace the silent fallback:

```python
    preset_css = TEMPLATES.get(template, TEMPLATES["academic"])
```

with:

```python
    if template not in TEMPLATES:
        raise ValueError(
            f"unknown template {template!r}; expected one of {sorted(TEMPLATES)}"
        )
    preset_css = TEMPLATES[template]
```

Then read `dashboard/template_plugin.py` and find where it calls `apply_template`. It performs the same silent fallback itself — make it return HTTP 400 with the error message rather than letting the `ValueError` become a 500. Match the error-response style already used in that file.

- [ ] **Step 4: Stop custom CSS escaping its block**

In the same function, where `custom_css` is interpolated, sanitise it first:

```python
def _sanitise_custom_css(css: str) -> str:
    """Prevent custom CSS from closing its <style> block.

    `</style>` inside a style element ends it, so anything after becomes
    live markup in a document that gets shared with reviewers.
    """
    return re.sub(r"</\s*style", "<\\/style", css, flags=re.IGNORECASE)
```

and apply it at the interpolation point.

- [ ] **Step 5: Add h5py so a real skip becomes a real test**

In `requirements.txt`, add after `meshio==5.3.5`:

```
# h5py: the generic-HDF5 reader path in scripts/data_loader.py. Without it
# tests/test_data_loader.py skips, which hid a reader failure rather than
# reporting one.
h5py>=3.10
```

Then install and see what the previously-skipped tests actually do:

```bash
venv/bin/python -m pip install -q "h5py>=3.10"
venv/bin/python -m pytest tests/test_data_loader.py -v -k "hdf5 or h5"
```

Record the result. **If a test now FAILS rather than passes, that is the point** — the skip was hiding a defect. Do not re-skip it. Report the failure and fix the reader if the fix is small; if it is not small, report it and stop for guidance rather than masking it.

- [ ] **Step 6: Remove the orphaned function**

```bash
grep -rn "_rewrite_paperview_asset_urls_for_pdf" --include="*.py" . | grep -v venv | grep -v __pycache__
```

Expect matches only in `dashboard/compile_plugin.py` (the definition) and `tests/test_compile_plugin.py`. If any production caller exists, STOP and report. Otherwise delete the function and its tests.

- [ ] **Step 7: Run the full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Record the exact counts. The skip count must drop by at least 1 (the h5py skip).

- [ ] **Step 8: Commit and open the PR**

```bash
git checkout -B fix/correctness-batch main
git add requirements.txt _extensions/4dpaper/export_templates.py dashboard/template_plugin.py \
        dashboard/compile_plugin.py tests/test_export_templates.py tests/test_compile_plugin.py
git commit -m "fix: reject unknown templates, contain custom CSS, add h5py

Four items from the v0.1.3 whole-release review:
- an unknown template name silently rendered as 'academic'
- custom_css could close its <style> block and inject markup into a
  document meant to be shared
- the h5py skip hid a reader path rather than testing it
- _rewrite_paperview_asset_urls_for_pdf had no production callers

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin fix/correctness-batch
gh pr create --title "fix: correctness batch from the v0.1.3 review" --body "Four small defects from the whole-release review. See docs/superpowers/specs/2026-09-14-backend-restructure-design.md section 10.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 2: Make the project an installable package

This is the keystone. `_extensions/4dpaper/4dpaper.py` cannot be imported because its directory begins with a digit and the project has no package metadata. That single fact forces the 13 importlib shims and the 9 `sys.path` edits that Task 3 deletes.

**Files:**
- Create: `pyproject.toml`
- Modify: `_extensions/4dpaper/4dpaper.py` (remove `sys.path` injection and the `os.execv` re-launch)
- Test: `tests/test_packaging.py` *(new)*

**Interfaces:**
- Consumes: nothing.
- Produces: `pip install -e .` works; `import fourdpaper` succeeds with no `sys.path` manipulation. Task 3 and Task 4 depend on this.

- [ ] **Step 1: Read what currently happens at import**

```bash
sed -n '1,60p' _extensions/4dpaper/4dpaper.py
```

Note the three `sys.path.insert` calls, the `os.execv` re-launch into `.venv`, and the `from dashboard.document_signing import ...` — the Quarto extension reaching backwards into the server package.

- [ ] **Step 2: Write the failing test**

Create `tests/test_packaging.py`:

```python
"""The project must be importable as a package, with no sys.path surgery."""
from __future__ import annotations

import subprocess
import sys


def test_package_imports_without_path_manipulation():
    """A fresh interpreter must import the library with no sys.path edits.

    Thirteen importlib shims and nine sys.path edits exist in the test
    suite solely because this was not true.
    """
    code = "import fourdpaper; print(fourdpaper.__name__)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "fourdpaper" in out.stdout


def test_extension_modules_are_importable():
    from fourdpaper import parser, render, state
    assert hasattr(parser, "parse_shortcodes")
    assert hasattr(render, "generate_png_figure")
    assert hasattr(state, "load_styles")
```

- [ ] **Step 3: Run it and confirm it fails**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'fourdpaper'`.

- [ ] **Step 4: Decide the package shape, then write pyproject.toml**

The library code lives in `_extensions/4dpaper/lib/`. Do **not** move it — this phase forbids module moves. Instead map it to an importable name from `pyproject.toml`.

Create `pyproject.toml`:

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
# cannot be imported by its own path. Map it to an importable name here
# rather than moving it — module moves belong to Phase 2.
package-dir = { fourdpaper = "_extensions/4dpaper/lib", dashboard = "dashboard" }

[tool.setuptools.packages.find]
where = ["."]
include = ["dashboard*"]

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

- [ ] **Step 5: Install and check the mapping actually works**

```bash
venv/bin/python -m pip install -e . 2>&1 | tail -3
venv/bin/python -c "import fourdpaper, fourdpaper.parser; print('ok', fourdpaper.parser.__file__)"
```

If `package-dir` with a digit-prefixed source path does not work under your setuptools version, do NOT move the directory. Report exactly what failed and propose the smallest alternative (for example a thin `fourdpaper/` package of re-export modules). Get confirmation before choosing.

- [ ] **Step 6: Remove the sys.path surgery and the execv re-launch**

In `_extensions/4dpaper/4dpaper.py`, delete the three `sys.path.insert` calls and the entire `os.execv` re-launch block (roughly lines 19-46, including the safety check that exists only to make the re-launch safe). Replace the `from lib.X import ...` imports with `from fourdpaper.X import ...`.

The `os.execv` existed to re-enter the project venv. That is now `pip install -e .` inside the venv Quarto already uses, via `QUARTO_PYTHON` which `dashboard/utils.py` already sets.

- [ ] **Step 7: Verify the pre-render hook still runs under Quarto**

This is the risk in this task — the hook runs as a Quarto subprocess, not under pytest.

```bash
venv/bin/python -m pytest tests/test_export_pipeline.py -v
```

Expected: pass. These shell out to real `quarto render`, so they exercise the hook exactly as Quarto invokes it. If they fail, the import rewiring is wrong — fix it before continuing.

- [ ] **Step 8: Run both test targets**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
venv/bin/python -m pytest tests/ -q
```

Expected: packaging tests pass; suite count unchanged or higher, no new skips.

- [ ] **Step 9: Update the Dockerfile to install the package**

Read `Dockerfile` and find where `requirements.txt` is installed. Add an editable install of the project after it, so the container gets the same import path as local and CI. Match the file's existing style.

- [ ] **Step 10: Commit and open the PR**

```bash
git checkout -B feat/installable-package main
git add pyproject.toml _extensions/4dpaper/4dpaper.py tests/test_packaging.py Dockerfile
git commit -m "feat: make the project an installable package

_extensions/4dpaper/4dpaper.py could not be imported, because its
directory starts with a digit and the project had no package metadata.
That forced three sys.path injections, an os.execv re-launch into the
venv, and thirteen importlib shims across the test suite.

Maps the library to an importable name without moving it -- module
moves belong to Phase 2.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin feat/installable-package
gh pr create --title "feat: installable package" --body "Keystone of Phase 1: makes the library importable, which is what lets the test suite be rebuilt.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 3: Delete the importlib shims and sys.path edits

**Files:**
- Modify: `tests/test_camera_lock.py`, `tests/test_controls_strip.py`, `tests/test_export_templates.py`, `tests/test_extension.py`, `tests/test_graph_camera.py`, `tests/test_panel_sync.py`, `tests/test_styles.py`, `tests/test_timeseries.py`

**Interfaces:**
- Consumes: `import fourdpaper.*` from Task 2.
- Produces: zero `spec_from_file_location` and zero `sys.path` in `tests/`.

- [ ] **Step 1: Inventory exactly what must go**

```bash
grep -rn "spec_from_file_location" tests/*.py
grep -rn "sys.path" tests/*.py
```

Expected: 13 and 9 respectively. Record both lists — they are your checklist.

- [ ] **Step 2: Write the guard test that keeps them from coming back**

Add to `tests/test_packaging.py`:

```python
import pathlib


def test_no_importlib_shims_remain_in_tests():
    """Each shim exists only because the package was not importable.

    They regenerate quietly: v0.1.3 added two more while the package was
    still unimportable.
    """
    offenders = []
    for p in pathlib.Path("tests").rglob("test_*.py"):
        text = p.read_text(encoding="utf-8")
        if "spec_from_file_location" in text:
            offenders.append(str(p))
    assert not offenders, f"importlib shims remain in: {offenders}"


def test_no_sys_path_manipulation_in_tests():
    offenders = []
    for p in pathlib.Path("tests").rglob("test_*.py"):
        if "sys.path" in p.read_text(encoding="utf-8"):
            offenders.append(str(p))
    assert not offenders, f"sys.path edits remain in: {offenders}"
```

- [ ] **Step 3: Run and confirm both fail**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v -k "shims or sys_path"
```

Expected: both FAIL, listing the 8 files.

- [ ] **Step 4: Replace each shim with a direct import**

Work file by file through the Step 1 list. In each, delete the `_load_*()` helper and its `importlib` imports, and replace call sites with a module-level import. For example in `tests/test_graph_camera.py`, `_load_parser()` becomes:

```python
from fourdpaper import parser
```

and `_load_parser().parse_graph_shortcodes(text)` becomes `parser.parse_graph_shortcodes(text)`.

Do them one file at a time, running that file's tests after each:

```bash
venv/bin/python -m pytest tests/<file> -q
```

Do not proceed to the next file until the current one passes. If a module genuinely cannot be imported by name, STOP and report which one — it means Task 2's mapping is incomplete.

- [ ] **Step 5: Confirm the guards now pass**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v
```

- [ ] **Step 6: Full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: same pass count as after Task 2, no new skips. The count must not DROP — a dropped test means a shim was deleted along with the tests that used it.

- [ ] **Step 7: Commit and open the PR**

```bash
git checkout -B refactor/delete-test-shims main
git add tests/
git commit -m "refactor: import modules directly in tests

Deletes 13 spec_from_file_location shims across 8 files and 9 sys.path
edits, all of which existed only because the package was not importable.

Adds guards so they do not regenerate -- v0.1.3 added two more while the
underlying cause was unfixed.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin refactor/delete-test-shims
gh pr create --title "refactor: delete test importlib shims" --body "13 shims, 9 sys.path edits, plus guards against regrowth.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 4: conftest.py, shared fixtures, and the five dead tests

Five tests in `tests/test_extension.py` (lines 651, 686, 725, 749, 781) gate on `/data/tutorials/NiedererEtAl2012/Niederer.foam` — an absolute path that exists on no machine, in no CI, and in no image. They report as "skipped", which reads as conditional. They are unreachable. The correct fixture, `examples/niederer/data/niederer/` (8 timesteps, 5 fields, 3.2 MB), is committed.

**Files:**
- Create: `tests/conftest.py`, `tests/fixtures/__init__.py`, `tests/fixtures/niederer.py`
- Modify: `tests/test_extension.py`

**Interfaces:**
- Consumes: `fourdpaper` imports from Task 2.
- Produces: fixtures `niederer_case`, `niederer_sim`, `project_root` available to every test. Task 7's harness depends on `niederer_case`.

- [ ] **Step 1: Write the fixture module**

Create `tests/fixtures/__init__.py` (empty) and `tests/fixtures/niederer.py`:

```python
"""Locators for the committed example case.

The case is a real, redistributable 8-timestep VTK series under
examples/niederer/. Tests must point here rather than at an absolute path
on one developer's machine.
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

    A missing fixture must fail, never skip: skipping is what let five
    tests sit unreachable for months.
    """
    if not NIEDERER_SERIES.is_file():
        raise AssertionError(
            f"committed example case missing at {NIEDERER_SERIES}. "
            "It is tracked in git; check out the full repository."
        )
    return NIEDERER_SERIES
```

- [ ] **Step 2: Write conftest.py**

Create `tests/conftest.py`:

```python
"""Shared fixtures.

Before this file existed, each test module hand-rolled its own module
loading and setup, which is how the suite accreted 35 skip hatches.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.fixtures.niederer import NIEDERER_SERIES, assert_case_present


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def niederer_case() -> Path:
    """Path to the committed example .vtk.series. Fails if absent."""
    return assert_case_present()


@pytest.fixture(scope="session")
def niederer_sim(niederer_case):
    """A loaded SimulationData for the committed example case."""
    from scripts.data_loader import SimulationData
    return SimulationData(str(niederer_case)).load()
```

- [ ] **Step 3: Write a test proving the fixture is real**

Add to `tests/test_packaging.py`:

```python
def test_committed_example_case_loads(niederer_sim):
    """The fixture the five previously-dead tests should have used."""
    from tests.fixtures.niederer import EXPECTED_FIELDS, EXPECTED_STEPS
    assert niederer_sim.n_steps == EXPECTED_STEPS
    assert EXPECTED_FIELDS.issubset(set(niederer_sim.fields))
```

- [ ] **Step 4: Run it**

```bash
venv/bin/python -m pytest tests/test_packaging.py -v -k example_case
```

Expected: PASS, proving the fixture loads before you repoint anything at it.

- [ ] **Step 5: Repoint the five dead tests**

In `tests/test_extension.py`, find each of the five occurrences of:

```python
        case_path = Path("/data/tutorials/NiedererEtAl2012/Niederer.foam")
        if not case_path.exists():
            pytest.skip("Niederer case not available")
```

Replace each with use of the `niederer_case` fixture — add `niederer_case` to the test's parameters and use it as the source path. Delete the `pytest.skip`.

These tests were written against an OpenFOAM `.foam` case and will now run against a `.vtk.series`. **Expect some to fail** on assumptions specific to the old case (field names, timestep counts, `part=` arguments). That is the point: they have never run. For each failure, decide and record in your report:
- the assertion is genuinely wrong for this fixture → update the assertion to what is correct for it;
- the test is meaningless without an OpenFOAM case → **delete it** and say so, rather than re-skipping.

Do not reintroduce a skip under any circumstances.

- [ ] **Step 6: Run the repointed tests**

```bash
venv/bin/python -m pytest tests/test_extension.py -v
```

Record which of the five pass, which were adjusted, and which were deleted with reasoning.

- [ ] **Step 7: Full suite**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: skip count drops by 5. Pass count rises by however many of the five now run.

- [ ] **Step 8: Commit and open the PR**

```bash
git checkout -B test/conftest-and-real-fixtures main
git add tests/conftest.py tests/fixtures/ tests/test_extension.py tests/test_packaging.py
git commit -m "test: add conftest and point dead tests at the real fixture

Five tests gated on /data/tutorials/NiedererEtAl2012/Niederer.foam, an
absolute path present on no machine and in no CI run. They reported as
skipped, which reads as conditional; they were unreachable.

The correct fixture is committed at examples/niederer. A missing fixture
now fails rather than skipping.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/conftest-and-real-fixtures
gh pr create --title "test: conftest and real fixtures" --body "Adds the project's first conftest.py and makes five unreachable tests run.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 5: Resolve the remaining skip hatches

**Files:**
- Modify: whichever test files hold the remaining hatches
- Create: `tests/test_no_silent_skips.py`

**Interfaces:**
- Consumes: fixtures from Task 4.
- Produces: every remaining skip is deliberate, documented, and enumerated in one allowlist.

- [ ] **Step 1: Enumerate what is left**

```bash
venv/bin/python -m pytest tests/ -q -rs 2>&1 | grep "^SKIPPED"
grep -rn "pytest.skip\|importorskip\|skipif" tests/ --include="*.py"
```

Record every one. After Tasks 1 and 4 the runtime skips should be roughly: 1 Playwright gate, 2 Quick Export gates, 1 HDF5 fixture, 1 `.foam` fixture.

- [ ] **Step 2: Write the enforcement test**

Create `tests/test_no_silent_skips.py`:

```python
"""Every skip must be deliberate and enumerated.

The suite once reported 11 skips, of which 5 were unreachable tests and
2 were environment accidents. A skip that nobody enumerated is a test
nobody knows is missing.
"""
from __future__ import annotations

import pathlib
import re

# Each entry: (file, reason). Adding one requires justifying it here.
ALLOWED_SKIPS = {
    ("tests/e2e/test_dashboard_split.py", "browser E2E, gated on PLAYWRIGHT_E2E in CI"),
    ("tests/e2e/test_quick_export.py", "needs a running Quick Export server"),
}

SKIP_RE = re.compile(r"pytest\.skip|importorskip|mark\.skipif")


def test_only_allowed_files_contain_skips():
    allowed_files = {f for f, _ in ALLOWED_SKIPS}
    offenders = []
    for p in sorted(pathlib.Path("tests").rglob("test_*.py")):
        rel = p.as_posix()
        if rel in allowed_files:
            continue
        if SKIP_RE.search(p.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, (
        "skips found outside the allowlist: " + ", ".join(offenders) +
        " — make the test run, delete it, or justify it in ALLOWED_SKIPS"
    )
```

- [ ] **Step 3: Run it and see the real list**

```bash
venv/bin/python -m pytest tests/test_no_silent_skips.py -v
```

Expected: FAIL, naming every file still holding a skip.

- [ ] **Step 4: Resolve each offender**

For each file the test names, choose one and record the choice in your report:
1. **Make it run** — preferred. The HDF5 fixture skip (`tests/test_data_loader.py`) is likely fixable now that Task 1 added `h5py`: the message was "Could not deduce file format from path", suggesting the fixture needs a reader hint rather than a missing library.
2. **Delete it** — if the test cannot run anywhere and covers nothing else reaches.
3. **Add to `ALLOWED_SKIPS`** — only for genuine environment gates like browser E2E, with a one-line reason.

The `.foam` fixture skip in `tests/test_render_case_preview.py` references CLAUDE.md section 6.0, which records that no redistributable OpenFOAM fixture exists. Either repoint that test at `niederer_case` if it does not actually require OpenFOAM specifics, or allowlist it with that reason.

- [ ] **Step 5: Confirm**

```bash
venv/bin/python -m pytest tests/test_no_silent_skips.py -v
venv/bin/python -m pytest tests/ -q -rs 2>&1 | tail -6
```

Expected: the enforcement test passes, and every remaining runtime skip maps to an `ALLOWED_SKIPS` entry.

- [ ] **Step 6: Commit and open the PR**

```bash
git checkout -B test/no-silent-skips main
git add tests/
git commit -m "test: enumerate every skip, resolve the rest

A skip nobody enumerated is a test nobody knows is missing. Remaining
skips are now listed with a reason, and adding one requires justifying
it in the allowlist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/no-silent-skips
gh pr create --title "test: enumerate every skip" --body "Resolves the remaining skip hatches and adds an allowlist gate.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 6: CI gates and the data policy

**Files:**
- Create: `.gitattributes`
- Modify: `.github/workflows/pr-regressions.yml`, `.github/workflows/docker-publish.yml`, `requirements-e2e.txt`

**Interfaces:**
- Consumes: `[tool.ruff]` / `[tool.mypy]` config from Task 2's `pyproject.toml`.
- Produces: ruff, mypy, and `PLAYWRIGHT_E2E=1` enforced on every PR and on the release gate.

- [ ] **Step 1: See how much ruff and mypy currently complain**

```bash
venv/bin/python -m pip install -q ruff mypy
venv/bin/python -m ruff check . 2>&1 | tail -20
venv/bin/python -m ruff check . 2>&1 | grep -c "^" 
```

Record the counts. If ruff reports more than roughly 50 findings, do NOT fix them all here — that would bury the gate in unrelated churn. Instead narrow the `select` list in `pyproject.toml` to what passes cleanly plus `F` (real errors), note the deferred rules in your report, and widen it in a later phase.

- [ ] **Step 2: Fix what the chosen rule set reports**

```bash
venv/bin/python -m ruff check --fix .
venv/bin/python -m ruff check .
```

Expected: clean. Review the auto-fixes with `git diff` before accepting — do not blind-commit formatting changes to files this phase should not touch.

- [ ] **Step 3: Run mypy and scope it**

```bash
venv/bin/python -m mypy dashboard 2>&1 | tail -20
```

mypy on an untyped codebase reports a great deal. Scope it to something enforceable now: start with `dashboard/` only, `ignore_missing_imports = true`, and no strictness flags. Record in your report what you scoped it to and why.

- [ ] **Step 4: Add the gates to both workflows**

In `.github/workflows/pr-regressions.yml`, after the dependency install step and before the test step:

```yaml
      - name: Lint
        run: |
          python -m pip install ruff mypy
          python -m ruff check .
          python -m mypy dashboard
```

Set `PLAYWRIGHT_E2E: "1"` in the test step's `env:` block alongside `PYVISTA_OFF_SCREEN`, and add a Playwright browser install step before it:

```yaml
      - name: Install Playwright browsers
        run: python -m playwright install --with-deps chromium
```

Apply the same three changes to the `verify` job in `.github/workflows/docker-publish.yml`. The two workflows were brought to parity in v0.1.3 — keep them that way, and verify by diffing their steps.

- [ ] **Step 5: Add the LFS policy**

Create `.gitattributes`:

```
# Simulation fixtures can be large. Anything matching these patterns is
# stored via Git LFS so the repository stays clonable. Current fixtures
# (3.2 MB niederer, 5.5 MB tests/data) are small enough not to need it --
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

**Important:** this affects only files added from now on. Do NOT run `git lfs migrate` — rewriting a published repository's history breaks every existing clone. Verify existing tracked fixtures are unaffected:

```bash
git status --porcelain
```

Expected: only `.gitattributes` as new. If existing files show as modified, stop and report.

- [ ] **Step 6: Confirm E2E actually runs rather than skipping**

```bash
PLAYWRIGHT_E2E=1 venv/bin/python -m pytest tests/e2e/test_dashboard_split.py -v 2>&1 | tail -10
```

Record the result. If it fails for a real reason, that is a genuine finding — report it rather than reverting the gate.

- [ ] **Step 7: Full suite and commit**

```bash
venv/bin/python -m pytest tests/ -q
git checkout -B ci/lint-and-e2e-gates main
git add .gitattributes .github/workflows/ pyproject.toml requirements-e2e.txt
git commit -m "ci: enforce ruff, mypy and browser E2E on both gates

The browser tests were the only layer that could catch a dead figure and
they were disabled everywhere, which is how the viewer_logic.js
regression shipped.

Adds an LFS policy for future fixture data. Existing history is left
alone deliberately.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin ci/lint-and-e2e-gates
gh pr create --title "ci: lint, type and browser E2E gates" --body "Enables ruff, mypy and PLAYWRIGHT_E2E on both the PR gate and the release gate, and adds the LFS policy.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 7: The cross-target fidelity harness

The heart of the phase. This task's PR is **expected to be red** — a harness that passes on first run has not been shown to detect anything.

**Files:**
- Create: `tests/test_fidelity.py`
- Modify: `requirements-e2e.txt` (Pillow)

**Interfaces:**
- Consumes: `niederer_case` fixture (Task 4); `fourdpaper.render` (Task 2).
- Produces: `warm_fraction()` and `render_pair()`, used by Task 8 to prove the fix.

**Detection method, already validated.** A strict pixel comparison cannot work: vtk.js and offscreen VTK differ in antialiasing, lighting and resolution. What does work is the *warm-pixel fraction* of the mesh region. Measured on the existing `niederer-slab` figure pair: **HTML 5.0%, PNG 20.1%** — a 15-point gap caused purely by the `clim` divergence, far outside any rendering-difference noise.

- [ ] **Step 1: Add Pillow**

Add `Pillow>=10.0` to `requirements-e2e.txt` and install:

```bash
venv/bin/python -m pip install -q "Pillow>=10.0"
```

- [ ] **Step 2: Write the harness**

Create `tests/test_fidelity.py`:

```python
"""Cross-target fidelity: a figure must read the same in HTML and in PDF.

The HTML path scales scalars across every timestep (time_global_range),
while the PNG path that feeds PDF export lets PyVista auto-scale to a
single timestep. Same data, same timestep, different colours.

A strict pixel comparison cannot work here -- vtk.js and offscreen VTK
differ in antialiasing and lighting. The warm-pixel fraction of the mesh
region does work: measured 5.0% (HTML) against 20.1% (PNG) on the
committed example, a gap far outside rendering noise.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest
from PIL import Image

FIELD = "activationTime"
TIME_SPEC = "mid"
WARM_FRACTION_TOLERANCE = 0.05


def warm_fraction(path: pathlib.Path, crop_top_fraction: float = 0.0) -> float:
    """Fraction of non-background pixels that are warm (red-dominant).

    Directly reflects where a value sits in the colourmap, so a change in
    scalar range moves it sharply while antialiasing does not.
    """
    arr = np.asarray(Image.open(path).convert("RGB")).astype(float)
    if crop_top_fraction:
        arr = arr[int(arr.shape[0] * crop_top_fraction):, :]
    mask = arr.sum(axis=2) < 700          # drop near-white background
    px = arr[mask]
    assert len(px) > 500, f"{path.name}: too few mesh pixels ({len(px)}) — did it render?"
    return float((px[:, 0] > px[:, 2] + 20).mean())


@pytest.fixture(scope="module")
def render_pair(niederer_case, tmp_path_factory):
    """Render the same figure to HTML and PNG, and screenshot the HTML."""
    from playwright.sync_api import sync_playwright

    from fourdpaper.render import generate_html_figure, generate_png_figure

    out = tmp_path_factory.mktemp("fidelity")
    html_path = out / "fig.html"
    png_path = out / "fig.png"
    shot_path = out / "shot.png"

    common = dict(
        src_path=niederer_case, field=FIELD, time_spec=TIME_SPEC,
        fig_id="fidelity-probe", background="white", axis_color="black",
        cmap="coolwarm", show_colorbar=True, decimate="none",
    )
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
    return {"html": html_path, "png": png_path, "shot": shot_path}


def test_html_figure_actually_renders(render_pair):
    """Guards the guard: a blank canvas must not silently pass the comparison."""
    assert warm_fraction(render_pair["shot"], crop_top_fraction=0.06) >= 0.0
    assert render_pair["shot"].stat().st_size > 5000


def test_html_and_pdf_agree_on_colour_scale(render_pair):
    """The core invariant: the same figure must read the same in both targets."""
    html_warm = warm_fraction(render_pair["shot"], crop_top_fraction=0.06)
    png_warm = warm_fraction(render_pair["png"])
    assert abs(html_warm - png_warm) <= WARM_FRACTION_TOLERANCE, (
        f"HTML and PDF disagree on colour scale: "
        f"HTML warm={html_warm:.3f}, PNG warm={png_warm:.3f}, "
        f"difference {abs(html_warm - png_warm):.3f} exceeds {WARM_FRACTION_TOLERANCE}"
    )
```

- [ ] **Step 3: Run it and confirm it FAILS**

```bash
venv/bin/python -m pytest tests/test_fidelity.py -v
```

**Expected: `test_html_and_pdf_agree_on_colour_scale` FAILS**, reporting a difference well above 0.05. Record the exact numbers — they are the evidence that the harness detects the real defect.

If it PASSES, the harness is not measuring what it must. Do not proceed. Report the numbers and investigate: check that `FIELD` is embedded in the HTML, that the screenshot is not blank, and that `generate_png_figure` and `generate_html_figure` received the same `time_spec`.

- [ ] **Step 4: Confirm the signature call arguments are right**

The two generator signatures differ. Read them before assuming:

```bash
venv/bin/python -c "
import inspect
from fourdpaper.render import generate_html_figure, generate_png_figure
print('PNG :', inspect.signature(generate_png_figure))
print('HTML:', inspect.signature(generate_html_figure))
"
```

Adjust the `common` dict and the per-call keyword arguments in the fixture to match the real signatures exactly.

- [ ] **Step 5: Commit the deliberately red PR**

```bash
git checkout -B test/fidelity-harness main
git add tests/test_fidelity.py requirements-e2e.txt
git commit -m "test: add the cross-target fidelity harness

Asserts that a figure reads the same in HTML and in the PNG that feeds
PDF export. It fails today, which is the point: the HTML path scales
scalars across all timesteps while the PNG path scales to one, so
activationTime renders pale blue in HTML and red in PDF.

Compares warm-pixel fraction rather than pixels, because vtk.js and
offscreen VTK differ in antialiasing and lighting. Measured gap on the
committed example: 5.0% against 20.1%.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin test/fidelity-harness
gh pr create --title "test: cross-target fidelity harness (expected red)" --body "**This PR is expected to fail CI.** The harness detects a real divergence that the next PR fixes.

A harness that passes on first run has not been shown to detect anything.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 6: Report the failure numbers**

Record in your report the exact HTML and PNG warm fractions and their difference. Task 8 is judged against these.

---

### Task 8: Fix the colour-scale divergence

**Files:**
- Modify: `_extensions/4dpaper/lib/render.py`

**Interfaces:**
- Consumes: the harness from Task 7.
- Produces: `generate_png_figure` and `generate_html_figure` resolve scalar range identically.

- [ ] **Step 1: Read both call sites**

```bash
sed -n '625,640p' _extensions/4dpaper/lib/render.py
sed -n '695,710p' _extensions/4dpaper/lib/render.py
grep -n "time_global_range" _extensions/4dpaper/lib/render.py | head
```

Line ~633 is in `generate_png_figure`, line ~703 in `generate_html_figure`. Neither passes `clim` to `_add_mesh_auto`, so both fall back to PyVista's per-timestep auto-scaling for the static render — but only the HTML path computes `time_global_range` and hands it to the JS controls, which apply it once the page loads. Hence the divergence.

- [ ] **Step 2: Add one range resolver used by both paths**

Add near the top of `_extensions/4dpaper/lib/render.py`, after the imports:

```python
def _resolve_scalar_range(sim, field: str, step_indices: list[int] | None = None):
    """Scalar range for a field, spanning the given steps.

    Both render targets must ask the same question and get the same
    answer. When they resolved range independently, the HTML path scaled
    across all timesteps and the PNG path scaled to one, so identical
    values mapped to different colours in HTML and PDF.

    Returns None when the field is absent or has no finite values, so the
    caller falls back to PyVista's own behaviour.
    """
    import numpy as _np

    if not field:
        return None
    steps = step_indices if step_indices is not None else range(sim.n_steps)
    lo, hi = float("inf"), float("-inf")
    for i in steps:
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

- [ ] **Step 3: Pass the resolved range at both call sites**

In `generate_png_figure`, before its `_add_mesh_auto` call, resolve the range from the same simulation object it already loaded, and pass it:

```python
    _clim = _resolve_scalar_range(sim, field)
    _add_mesh_auto(pl, surface, field=field, cmap=cmap,
                   show_colorbar=show_colorbar, axis_color=axis_color, clim=_clim)
```

Do the same in `generate_html_figure`. Read each function first to find the correct local variable holding the loaded simulation — do not assume it is named `sim` in both.

`_add_mesh_auto` already accepts `clim` and forwards it only when not None (`_extensions/4dpaper/lib/mesh.py`), so a `None` return preserves today's behaviour exactly.

- [ ] **Step 4: Run the harness — it must now pass**

```bash
venv/bin/python -m pytest tests/test_fidelity.py -v
```

Expected: PASS, with the warm-fraction difference inside 0.05. Record the new numbers beside Task 7's.

- [ ] **Step 5: Check nothing else moved**

```bash
venv/bin/python -m pytest tests/ -q
```

Expected: no failures. Figure-related tests asserting on generated output may legitimately change, since colours now differ from before. For each such failure, confirm the NEW behaviour is correct before updating the assertion, and say so in your report.

- [ ] **Step 6: Commit and open the PR**

```bash
git checkout -B fix/shared-scalar-range main
git add _extensions/4dpaper/lib/render.py
git commit -m "fix: resolve scalar range once for both render targets

The HTML path scaled scalars across every timestep while the PNG path
that feeds PDF export let PyVista auto-scale to one, so identical values
mapped to different colours. On the committed example, activationTime
rendered at 62.3% of the HTML span -- pale blue in HTML, bright red in
the PDF.

Both paths now ask one resolver and receive the same answer.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git push -u origin fix/shared-scalar-range
gh pr create --title "fix: shared scalar range across render targets" --body "Makes the fidelity harness from the previous PR pass. Both render paths now resolve scalar range through one function.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
gh pr checks --watch
```

---

### Task 9: Close the phase

**Files:**
- Modify: `VERSION`, `CHANGELOG.md`, `docs/superpowers/specs/2026-09-14-backend-restructure-design.md`

- [ ] **Step 1: Verify from a clean tree**

```bash
git checkout main && git pull
git status --porcelain
venv/bin/python -m pytest tests/ -q -rs 2>&1 | tail -8
```

Expected: no output from `git status`; zero failures; every remaining skip in `ALLOWED_SKIPS`.

- [ ] **Step 2: Record the phase's numbers**

```bash
venv/bin/python -m pytest tests/ -q \
  --cov=dashboard --cov=scripts --cov=_extensions/4dpaper --cov-report=term | tail -3
grep -rc "spec_from_file_location" tests/*.py | grep -v ":0" | wc -l
```

Expected: shim count zero. Record coverage against the 51% that closed Phase 0.

- [ ] **Step 3: Update VERSION and CHANGELOG**

Set `VERSION` to the next patch number and add a CHANGELOG entry covering: the installable package, the deleted shims and skips, the CI gates, and the colour-scale fix. Match the existing entry style — a short prose lead, then bullets.

State the colour-scale fix in user terms: figures in exported PDFs previously used a different colour scale from the same figure in HTML.

- [ ] **Step 4: Mark the phase done in the spec**

In `docs/superpowers/specs/2026-09-14-backend-restructure-design.md`, mark Phase 1 shipped with its version number, the way Phase 0 is marked. Move any Phase 1 item that was deferred into section 10.

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

- `pip install -e .` works; `import fourdpaper` needs no `sys.path` edits.
- Zero `spec_from_file_location` and zero `sys.path` in `tests/`, with guards preventing regrowth.
- Every remaining skip enumerated in `ALLOWED_SKIPS` with a reason.
- The five previously-unreachable tests run, or are deleted with recorded reasoning.
- ruff, mypy and `PLAYWRIGHT_E2E=1` enforced on both the PR gate and the release gate.
- `tests/test_fidelity.py` passes, and its failure before Task 8 is recorded as evidence it detects the defect.
- Working tree clean; phase tagged.

## Next

Phase 2 — `readers/`, `publish/`, `server/`. It depends on this phase's fidelity harness, which is what makes restructuring the render pipeline in Phase 3 survivable.
