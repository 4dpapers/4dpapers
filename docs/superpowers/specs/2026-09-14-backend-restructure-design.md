# 4Dpapers Backend Restructure — Design

Date: 2026-09-14
Status: Approved for planning
Releases: v1.1 → v1.2 → v1.3 → v2

## 1. Goal

Restructure the 4Dpapers backend into modules with declared contracts, so the
tool can underpin a series of publications. Four drivers, addressed in order of
ascending difficulty: build hygiene, reproducibility, safe changeability, and
agent-workability.

The frontend works today. It is preserved and extracted, not redesigned.

## 2. Core invariant

A figure must read the same in all three targets:

    dashboard preview  ≡  exported HTML  ≡  exported PDF

This is the product's defining promise. Every release is gated on it.

### 2.1 The invariant is broken today

Measured against `examples/niederer` (8 timesteps, 5 fields):

`lib/render.py:831` computes `time_global_range` — a scalar range spanning all
timesteps — for the HTML path. `lib/render.py:633` calls `_add_mesh_auto()` with
no `clim`, so the PNG path auto-scales to a single timestep.

| Field | PDF span as % of HTML span |
|---|---|
| `activationTime` | **62.3%** |
| `ionicCurrent` | 83.8% |
| `Jsi` | 86.5% |
| `Vm` | 97.2% |

Rendered consequence for `niederer-slab`: the HTML colorbar runs 0 → 0.0399 and
the activation front is pale blue; the PNG colorbar runs 0 → 0.0198 and the same
front is bright red. Same data, same timestep, opposite reading.

No test guards this. It ships in v0.1.2.

## 3. Audit findings

### 3.1 Structure

| Finding | Evidence |
|---|---|
| `sys.path` injection ×3 and an `os.execv` re-launch in the pre-render hook | `_extensions/4dpaper/4dpaper.py:19-53` |
| Quarto extension imports backwards into the server package | `4dpaper.py` → `dashboard.document_signing` |
| ~40 `_private` functions imported across module boundaries | `4dpaper.py:53-58` |
| Figure HTML/CSS/JS built by Python string concatenation | `lib/frontend.py:433-470` |
| Generated HTML patched by string replacement (`100vw`→`900px`) | `lib/render.py:838` |
| Figure state touched by 10 modules across 37 path-construction sites | `dashboard/`, `_extensions/` |
| `lib/render.py` 1272 lines; `lib/frontend.py` 817; `index.html` 2360 (1662 inline JS) | — |
| No `pyproject.toml`, ruff, mypy, or pre-commit | — |

### 3.2 Tests

432 pass, 11 skip, **48% coverage**, inverted — least-tested code is most important.

| Module | Coverage |
|---|---|
| `4dpaper.py` | 17% |
| `lib/render.py` | 39% (incl. the `clim` loop) |
| `lib/mesh.py` | 39% |
| `shortcuts_plugin`, `template_plugin`, `sync_plugin`, `export_templates`, `sign_rendered_html` | **0%** |

Root cause of test decay: **there is no `conftest.py`.** Because the package is
not installable, `4dpaper.py` cannot be imported, so seven test files hand-roll
ten `spec_from_file_location` shims, with nine `sys.path` edits, 18 `pytest.skip`
and 12 `pytest.importorskip` hatches, and zero shared fixtures.

Five tests in `test_extension.py` gate on `/data/tutorials/NiedererEtAl2012/Niederer.foam`
— an absolute path that exists nowhere. They are unreachable, not conditional.
The correct fixture (`examples/niederer/data/niederer/`, 3.2 MB, 8 steps, 5 fields)
is already committed.

`tests/e2e/` requires `PLAYWRIGHT_E2E=1`. No workflow sets it, so the only layer
that could catch a dead figure is disabled in CI — which is how the prior
`viewer_logic.js` regression shipped.

### 3.3 Feasibility validated

Headless Chromium renders a real generated figure with full WebGL 2.0: mesh,
colorbar, orientation axes, field selector, play button, time slider. The
fidelity harness is buildable. Verified 2026-09-14.

jinja2 3.1.6 is already present transitively via bokeh/panel — templates-as-files
costs no new dependency.

## 4. Architecture

```
readers/    source handle → mesh, timesteps, fields
figures/    kind          → .html | .png
publish/    document      → HTML | PDF-via-LaTeX
server/     HTTP + WebSocket surface
web/        frontend + the backend seam   (preserve; extract, don't redesign)
```

### 4.1 `readers/`

```python
class MeshSource(Protocol):
    n_steps: int
    time_values: Sequence[float]
    fields: Sequence[str]

    def mesh_at(self, step: int, part: str = "internalMesh") -> pv.DataSet: ...
    def field_range(self, field: str, steps: Iterable[int] | None = None) -> tuple[float, float]: ...
    def close(self) -> None: ...
```

One module per format family (`openfoam`, `vtk_family`, `surface`, `ensight`,
`cgns`, `exodus`, `xdmf`, `meshio_formats`), each registering its extensions.
Adding a format is one new file; no existing file is edited. Dissolves the
450-line `SimulationData` god-class.

Two deliberate choices:

- **`open_source()` takes a `SourceHandle`, not a `Path`.** This is not designing
  for a hypothetical. Readers already implement five inconsistent answers to
  "how do I get at these bytes": direct open; sibling scan (`processor*` globbed
  from `case_path.parent`, `data_loader.py:103,185`); temp staging with symlinks
  and a synthetic `_temp_reader.foam` (`:193-204`); gzip decompression (`:533`);
  and index-relative resolution (`:245`). The third forces a `cleanup()`/`__del__`
  lifecycle onto the class (`:468,485`) purely to delete temp dirs — and
  `__del__` teardown is non-deterministic and can fire during interpreter
  shutdown. `SourceHandle` names the thing that already exists in five copies
  and gives it one deterministic lifecycle:

      with open_source(handle) as src:
          mesh = src.mesh_at(0)

  Remote or streamed sources then become one new handle class. That is a
  consequence, not the justification.

- **`field_range(field, steps)` is in the contract.** There is exactly one way
  to ask a field's range, and it takes the steps you care about. This makes the
  `clim` divergence unrepresentable rather than merely fixed.

Depends on: pyvista, meshio.

### 4.2 `figures/`

```python
class FigureKind(Protocol):
    name: str
    def parse(self, attrs: Mapping[str, str]) -> FigureSpec: ...
    def render_html(self, spec: FigureSpec, ctx: RenderContext) -> Path: ...
    def render_png(self,  spec: FigureSpec, ctx: RenderContext) -> Path: ...
```

`RenderContext` carries the resolved source, style, camera, field state, output
dir, **and one `ScalarScale` resolved once and handed to both renderers.** The
two targets cannot disagree about colour scaling because they are never given
the chance to decide separately.

`figures/templates/` holds real `.html`/`.css`/`.js` files rendered through
jinja2. Eliminates the inline-style concatenation and the `100vw` string patch,
and makes the figure's JS lintable and diffable for the first time.

Kinds: `image`, `panel`, `timeseries`, `graph`, `video`, `subimages`, `graph_panel`.

Depends on: `readers/`, pyvista, jinja2.

### 4.3 `publish/`

Quarto orchestration: profile selection, render invocation, output validation,
template injection, signing. This is where the v1.1 LaTeX export lands properly.
`compile_plugin.py` is 557 lines today largely because it *is* the publish layer
wearing an HTTP costume.

Depends on: `figures/`, Quarto binary.

### 4.4 `server/`

Handlers only: parse request → call `publish/` or the state store → serialize.
No business logic, no path arithmetic.

One `FigureState` store replaces the 37 path-construction sites across 10
modules. Camera, field, colour and lock state get exactly one reader and one
writer.

Depends on: `publish/`, `FigureState`, tornado.

## 5. Data policy

A paper is self-contained; its data lives with it. That is what makes a paper
reproducible by a reviewer in five years. Pointing at data outside the paper
(`@shortcut/...`) remains a supported escape hatch with a known cost, not the
happy path.

Test fixtures live in the repository as runnable examples. `.gitattributes` with
an LFS threshold is configured now, while the repo is small. Current fixtures
(3.2 MB niederer, 5.5 MB `tests/data`) do not need LFS; the policy exists so the
next example case lands correctly instead of bloating history.

`examples/heart` (63 GB) stays gitignored. The 12.9 MB `_freeze` blob already in
history stays; rewriting a published repo's history is not worth 12.9 MB.

## 6. Releases

Behaviour change and structure change never occur in the same release.

Work ships in PR-sized batches, one reviewable idea each, CI green per PR.

### v1.0.3 — Land what is already built

The four in-flight features, released ahead of the test rebuild so finished work
is not held behind it.

| PR | Content |
|---|---|
| 1 | Delete `updatemenus.json`; land cache busting + `breakable-code.lua` |
| 2 | Land `4d-subimages` + `4d-graph-panel` |
| 3 | Land live file sync **and its first tests** (0% today) |
| 4 | Land LaTeX PDF export **and `export_templates` tests** (0% today) |

Tag **v1.0.3**.

### v1.1 — Foundation and honest tests

No module moves. No restructuring. No behaviour change except fidelity fixes.

| PR | Content | CI must prove |
|---|---|---|
| 5 | `pyproject.toml`, installable package | Import works with no `sys.path` edits |
| 6 | Delete 10 importlib shims, 9 `sys.path` edits, `os.execv` re-launch | Suite green and smaller |
| 7 | `conftest.py` + shared fixtures; repoint the 5 dead tests at `examples/niederer` | Those 5 tests **run** |
| 8 | Resolve the remaining skip/importorskip hatches | Skip count near zero |
| 9 | `.gitattributes`/LFS; ruff + mypy in CI; `PLAYWRIGHT_E2E=1` | New gates enforced |
| 10 | Cross-target fidelity harness | **Build fails** — the harness detects the bug |
| 11 | Fix `clim` and siblings | Harness green |

Ordering constraints: 5 → 6 → 7 (shims cannot go before the package exists;
`conftest` cannot go before imports work) and 10 → 11 (harness before fix, so the
fix is demonstrated rather than asserted).

PR 10 is deliberately a red build. A harness that passes on first run has not
been shown to detect anything.

Tag **v1.1** — the frozen behavioural baseline for every later release.

### v1.2 — Backend modules, lower risk

`readers/`, `publish/`, `server/`, each with a declared contract and no private
cross-imports. Tag **v1.2**.

### v1.3 — Render pipeline

`figures/` alone: kind registry, templates out of Python strings, public API
replacing the ~40 cross-imported private names. Isolated because this layer
broke once before, and because a regression here must be bisectable.
Tag **v1.3**.

### v2 — Frontend seam

Extract `index.html`'s 1662 inline JS lines alongside the twelve modules already
present. Formalize the postMessage protocol. Preserve behaviour.

## 7. Execution

Every batch is a pull request against `main`, reviewed before the next starts.
`pr-regressions.yml` already runs the full suite with Quarto and headless GL on
every PR; the ruff, mypy, `PLAYWRIGHT_E2E` and fidelity gates are added by the
PRs that create them (5, 9, 10) and enforced from then on.

Work is assigned by how much judgment it needs, not by size:

| Batch | Executor | Why |
|---|---|---|
| 1, 2 | Either | Landing tested work |
| 3, 4 | Opus | Deciding what to assert for two untested modules |
| 5–9 | Sonnet | Mechanical, fully specified, objective pass/fail |
| 10, 11 | Opus | Defining what "the same figure" means across targets, and setting perceptual tolerances that catch a 38% colour shift without failing on antialiasing |

## 8. Acceptance

Every release ends with the v1.1 fidelity suite green. "We did not lose what
works today" is a command that can be run, not a hope.

Per-release gates:

- Cross-target fidelity: camera, active field, timestep, scalar range, frame
  count, and perceptual image similarity agree across HTML and PNG.
- Functional browser gate: the compiled figure loads, the canvas renders, the
  play button advances frames, the field switcher swaps scalars.
- No new `pytest.skip` without an accompanying issue reference.
- ruff and mypy clean.

## 9. Non-goals

- Redesigning the frontend UI.
- Remote simulation execution. The `SourceHandle` contract keeps it possible;
  no implementation ships.
- Rewriting git history.
- Removing `why` comments. Comment density is already 3–4%, and the surviving
  comments (the `trame-vtk` pin rationale, the execv safety note) record
  knowledge nothing else in the repo holds. What is removed: comments that
  restate code, section-divider art, and docstrings describing history rather
  than contract.
