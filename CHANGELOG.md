# Changelog

## 0.1.3 — 2026-09-15

Feature release: native LaTeX PDF export, two grid shortcodes, live file sync,
and named HTML export templates. Also repairs a build break that had made 0.1.2
unreproducible, and restores the offline-export guarantee that the move to
LaTeX had quietly dropped.

- Export PDFs through Quarto's native LaTeX renderer instead of WeasyPrint, and
  add the texlive toolchain to the image. Removes the WeasyPrint dependency
  entirely.
- Add the `4d-subimages` and `4d-graph-panel` grid shortcodes.
- Add live file sync: file changes push to dashboard clients over a WebSocket.
- Add four named HTML export templates (academic, modern, compact, preprint)
  with an optional list-of-figures index. Their fonts are vendored locally, so
  they do not reintroduce the CDN dependency removed in 0.1.2.
- Fingerprint asset URLs after render, and let code blocks break across PDF
  pages.

### Fixed

- Pin `weasyprint` (since removed): the requirement was unpinned, so the 70.0
  release removed an API the export path used and CI began failing with no code
  change. 0.1.2 could no longer be rebuilt from source.
- Keep PDF export offline. Moving to Quarto's native renderer dropped both
  guards the WeasyPrint path had — pandoc fetches remote images during
  `--to pdf`, and when it cannot reach them the author saw a pandoc Lua
  traceback instead of a message naming the asset. Remote references are now
  refused before Quarto runs, following `{{< include >}}` directives, and
  covering Markdown, HTML, CSS `url()`, bare `@import`, and raw passthrough
  blocks. `FOURD_PDF_ALLOW_REMOTE=1` opts in.
- Stop grid layouts from hiding subfigures. An explicit `layout="COLSxROWS"`
  was used verbatim regardless of how many sources were supplied, and the
  fixed-height container clipped the overflow, so `4d-graph-panel` with six
  sources in a `2x2` layout silently dropped two figures from the paper.
- Reject cross-site WebSocket handshakes on the file-sync endpoint. Because
  local-dev mode sets no API key, any site the user visited could otherwise
  open a socket and read every file they edited.
- Escape figure captions in the generated list-of-figures. Entities were
  decoded and reinserted unescaped, so a caption written `&lt;script&gt;`
  became live markup in the exported document.
- Start the file-system watcher explicitly rather than at import, so importing
  the module no longer spawns a recursive watcher on the project root.

### Internal

- First test coverage for `sync_plugin` (0% → 71%) and `export_templates`
  (0% → 77%). Suite: 472 passing, overall coverage 48% → 51%.
- Give the release workflow the same environment as the PR workflow. It
  installed no Quarto, so it ran a weaker suite (15 skipped against 11) than
  the gate on pull requests — four export tests silently skipped in the
  workflow that guards the published image.
- Discover Quarto project templates via git in tests rather than hardcoding
  paths, two of which pointed into a gitignored directory and so could only
  pass on one machine.
- Remove the dead WeasyPrint URL fetcher, which had no production callers but
  four tests keeping a pinned dependency alive.

## 0.1.2 — 2026-07-16

Offline-hardening patch: the dashboard UI and PDF export now work with no
network access, which the first public build did not.

- Vendor every dashboard browser dependency — Tailwind, CodeMirror, the Phosphor
  icon font, and the Outfit / JetBrains Mono web fonts — instead of loading them
  from CDNs, so the editor renders correctly in air-gapped and egress-restricted
  containers. Drop the unused MathJax and polyfill.io includes.
- Make PDF export network-free: WeasyPrint no longer fetches remote assets by URL
  (set `FOURD_PDF_ALLOW_REMOTE=1` to opt back in), so a paper referencing an
  unreachable host can no longer hang the export silently. Shorten the render
  backstop timeout from 900s to 180s.
- Add real HTML-compile, standalone-HTML-export, and PDF-export regression tests
  that exercise the actual Quarto + WeasyPrint pipeline, plus an offline-assets
  guard, and run Quarto in CI so they execute on every pull request.

## 0.1.1 — 2026-07-15

Launch-hardening patch for the first public announcement.

- Replace the legacy writable-workspace Quick Export launcher with an opt-in
  isolated mode: read-only source, disposable workspace, and HTML-only output.
- Add `meshio` to the official image for the documented mesh readers.
- Render AI replies and workspace-controlled filenames as text to prevent
  same-origin HTML injection.
- Add a documentation link and AI data-handling notice to the dashboard.
- Add release test gating to the Docker publishing workflow.
- Replace the example-only Pages root with a responsive product landing page,
  embedded live figure, evidence-tiered format claims, and `/demo/` paper.
- Keep static papers interactive without calling dashboard-only camera and field
  persistence endpoints.
- Add security, support, contribution, citation, issue, and pull-request files.

## 0.1.0 — 2026-07-08

Initial tagged Docker release and Quarto-based interactive paper workflow.
