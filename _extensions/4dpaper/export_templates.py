"""
4Dpapers HTML Export Template Engine.

Provides:
  - TEMPLATES          : dict of preset CSS override strings
  - apply_template()   : inject CSS + optional figure index into a rendered HTML doc
  - inject_figure_index(): scan figcaptions and build a <table> index of figures

Usage (from template_plugin.py):
    from _extensions.4dpaper.export_templates import apply_template
    final_html = apply_template(html_text, template="academic", add_index=True)
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Preset CSS overrides — each one is injected as a <style> block into the
# exported HTML *after* the paperview.css base styles, so they always win.
# ---------------------------------------------------------------------------

TEMPLATES: dict[str, str] = {

    # ── Academic ────────────────────────────────────────────────────────────
    # Classic serif scientific paper. Matches the existing paperview.css style
    # closely, but lets users select it explicitly as a named preset.
    "academic": """\
/* 4Dpapers Export Template: Academic */
@import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:ital,wght@0,400;0,600;1,400&display=swap');
body {
  max-width: 800px !important;
  margin: 0 auto !important;
  padding: 4rem 5rem !important;
  font-family: 'Crimson Pro', Georgia, 'Times New Roman', serif !important;
  font-size: 12pt !important;
  line-height: 1.5 !important;
  color: #111 !important;
  background: #fff !important;
  text-align: justify !important;
}
h1, h2, h3, h4, h5 {
  font-family: 'Crimson Pro', Georgia, serif !important;
  font-weight: 600 !important;
  color: #000 !important;
}
h1.title { font-size: 22pt !important; text-align: center !important; margin-bottom: 0.4rem !important; }
h2 { font-size: 14pt !important; border-bottom: 1px solid #ccc !important; margin-top: 2.5rem !important; }
h3 { font-size: 12pt !important; font-style: italic !important; }
.abstract { margin: 2rem 8% !important; border-top: 1px solid #555 !important; border-bottom: 1px solid #555 !important; padding: 0.8rem 0 !important; font-size: 11pt !important; }
figure, .fourd-figure { margin: 2rem 0 !important; }
figcaption { font-style: italic !important; font-size: 10pt !important; color: #333 !important; text-align: center !important; margin-top: 0.6rem !important; }
.fourd-figure iframe { border: 1px solid #ddd !important; border-radius: 2px !important; }
table { border-collapse: collapse !important; width: 100% !important; font-size: 10.5pt !important; }
th { border-top: 2px solid #000 !important; border-bottom: 2px solid #000 !important; }
td { border-bottom: 1px solid #ddd !important; padding: 0.5rem !important; }
""",

    # ── Modern ──────────────────────────────────────────────────────────────
    # Clean sans-serif with accent headings and extra breathing room.
    "modern": """\
/* 4Dpapers Export Template: Modern */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body {
  max-width: 900px !important;
  margin: 0 auto !important;
  padding: 3rem 4rem !important;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
  font-size: 11pt !important;
  line-height: 1.65 !important;
  color: #1a1a2e !important;
  background: #fafafa !important;
  text-align: left !important;
}
h1, h2, h3, h4, h5 {
  font-family: 'Inter', sans-serif !important;
  font-weight: 700 !important;
  color: #0d0d1a !important;
}
h1.title { font-size: 26pt !important; text-align: left !important; letter-spacing: -0.02em !important; margin-bottom: 0.6rem !important; }
h2 { font-size: 15pt !important; color: #138a7c !important; border-left: 4px solid #138a7c !important; padding-left: 0.75rem !important; margin-top: 3rem !important; border-bottom: none !important; }
h3 { font-size: 12pt !important; font-weight: 600 !important; color: #1a1a2e !important; }
.abstract { margin: 2rem 0 !important; background: #f0faf9 !important; border-left: 4px solid #138a7c !important; border-top: none !important; border-bottom: none !important; padding: 1rem 1.25rem !important; border-radius: 0 4px 4px 0 !important; font-size: 11pt !important; }
figure, .fourd-figure { margin: 2.5rem 0 !important; }
figcaption { font-style: normal !important; font-size: 10pt !important; color: #555 !important; text-align: center !important; margin-top: 0.6rem !important; font-weight: 500 !important; }
.fourd-figure iframe { border: none !important; border-radius: 8px !important; box-shadow: 0 4px 24px rgba(0,0,0,0.08) !important; }
table { border-collapse: collapse !important; width: 100% !important; font-size: 10.5pt !important; }
th { background: #138a7c !important; color: #fff !important; border-top: none !important; border-bottom: none !important; padding: 0.6rem !important; font-weight: 600 !important; }
td { border-bottom: 1px solid #e8e8e8 !important; padding: 0.55rem !important; }
tr:hover td { background: #f5fffe !important; }
""",

    # ── Compact ─────────────────────────────────────────────────────────────
    # Dense, efficient layout for data-heavy technical reports.
    "compact": """\
/* 4Dpapers Export Template: Compact */
@import url('https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600&display=swap');
body {
  max-width: 720px !important;
  margin: 0 auto !important;
  padding: 2rem 3rem !important;
  font-family: 'Source Sans 3', 'Helvetica Neue', Arial, sans-serif !important;
  font-size: 10.5pt !important;
  line-height: 1.4 !important;
  color: #222 !important;
  background: #fff !important;
  text-align: left !important;
}
h1, h2, h3, h4, h5 {
  font-family: 'Source Sans 3', sans-serif !important;
  font-weight: 600 !important;
  color: #111 !important;
  margin-top: 1.5rem !important;
}
h1.title { font-size: 18pt !important; text-align: center !important; margin-bottom: 0.3rem !important; }
h2 { font-size: 12pt !important; border-bottom: 1px solid #ddd !important; padding-bottom: 0.15rem !important; margin-top: 1.8rem !important; }
h3 { font-size: 11pt !important; }
.abstract { margin: 1rem 0 !important; border: 1px solid #ddd !important; border-radius: 3px !important; padding: 0.6rem 0.8rem !important; font-size: 10pt !important; background: #fafafa !important; }
figure, .fourd-figure { margin: 1.25rem 0 !important; }
figcaption { font-style: italic !important; font-size: 9.5pt !important; color: #555 !important; text-align: left !important; margin-top: 0.3rem !important; }
.fourd-figure iframe { border: 1px solid #ddd !important; border-radius: 2px !important; }
table { border-collapse: collapse !important; width: 100% !important; font-size: 9.5pt !important; }
th { border-top: 1.5px solid #222 !important; border-bottom: 1.5px solid #222 !important; padding: 0.35rem 0.5rem !important; }
td { border-bottom: 1px solid #eee !important; padding: 0.3rem 0.5rem !important; }
p { margin-bottom: 0.6rem !important; }
""",

    # ── Preprint ─────────────────────────────────────────────────────────────
    # Two-column layout inspired by arXiv/IEEE style preprints.
    "preprint": """\
/* 4Dpapers Export Template: Preprint (two-column) */
@import url('https://fonts.googleapis.com/css2?family=Lato:ital,wght@0,400;0,700;1,400&display=swap');
body {
  max-width: 1050px !important;
  margin: 0 auto !important;
  padding: 2.5rem 3rem !important;
  font-family: 'Lato', 'Helvetica Neue', Arial, sans-serif !important;
  font-size: 10pt !important;
  line-height: 1.4 !important;
  color: #111 !important;
  background: #fff !important;
  text-align: justify !important;
  column-count: 2 !important;
  column-gap: 2.5rem !important;
  column-rule: 1px solid #e0e0e0 !important;
}
h1, h2, h3, h4, h5 {
  font-family: 'Lato', sans-serif !important;
  font-weight: 700 !important;
  break-after: avoid !important;
  color: #000 !important;
}
/* Title block spans both columns */
header.quarto-title-block, .quarto-title, .abstract, .quarto-title-meta {
  column-span: all !important;
}
h1.title { font-size: 18pt !important; text-align: center !important; margin-bottom: 0.3rem !important; }
h2 { font-size: 11pt !important; text-transform: uppercase !important; letter-spacing: 0.04em !important; border-bottom: 1.5px solid #333 !important; margin-top: 1.5rem !important; padding-bottom: 0.1rem !important; }
h3 { font-size: 10pt !important; font-style: italic !important; font-weight: 700 !important; }
.abstract { margin: 1rem 0 !important; border: none !important; font-size: 9.5pt !important; line-height: 1.35 !important; padding: 0 !important; }
figure, .fourd-figure { margin: 1rem 0 !important; break-inside: avoid !important; column-span: all !important; }
figcaption { font-style: italic !important; font-size: 9pt !important; color: #444 !important; text-align: center !important; margin-top: 0.3rem !important; }
.fourd-figure iframe { border: 1px solid #ccc !important; border-radius: 2px !important; }
table { border-collapse: collapse !important; width: 100% !important; font-size: 9pt !important; break-inside: avoid !important; }
th { border-top: 1.5px solid #222 !important; border-bottom: 1px solid #222 !important; padding: 0.3rem 0.4rem !important; }
td { border-bottom: 1px solid #e8e8e8 !important; padding: 0.25rem 0.4rem !important; }
p { margin-bottom: 0.5rem !important; }
""",

    # ── Custom ───────────────────────────────────────────────────────────────
    # Starter block for user-edited CSS; populated by the frontend JS.
    "custom": """\
/* 4Dpapers Export Template: Custom */
/* Edit the CSS below. Changes are applied live in the preview. */
body {
  max-width: 800px;
  margin: 0 auto;
  padding: 4rem 5rem;
  font-family: Georgia, serif;
  font-size: 12pt;
  line-height: 1.5;
  color: #111;
  background: #fff;
}
h1.title { text-align: center; }
h2 { border-bottom: 1px solid #ccc; margin-top: 2rem; }
.abstract { margin: 2rem 8%; border-top: 1px solid #888; border-bottom: 1px solid #888; padding: 0.8rem 0; }
figure, .fourd-figure { margin: 2rem 0; }
figcaption { font-style: italic; font-size: 10pt; color: #444; text-align: center; }
.fourd-figure iframe { border: 1px solid #ddd; border-radius: 2px; }
""",
}

# ---------------------------------------------------------------------------
# Figure Index Injection
# ---------------------------------------------------------------------------

_FIGCAPTION_RE = re.compile(
    r'<figcaption[^>]*>(.*?)</figcaption>',
    re.DOTALL | re.IGNORECASE,
)

_FIGURE_INDEX_STYLE = """\
<style id="fourd-figure-index-style">
.fourd-figure-index {
  margin: 2rem 0 2.5rem 0;
  padding: 1rem 0;
  border-top: 2px solid #333;
  border-bottom: 1px solid #ccc;
  page-break-inside: avoid;
}
.fourd-figure-index h2 {
  font-size: 12pt;
  margin: 0 0 0.75rem 0;
  padding: 0;
  border: none;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-weight: bold;
  color: #000;
}
.fourd-figure-index table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10pt;
  color: #222;
}
.fourd-figure-index td {
  padding: 0.3rem 0.5rem;
  border-bottom: 1px solid #eee;
  vertical-align: top;
}
.fourd-figure-index td:first-child {
  white-space: nowrap;
  font-weight: 600;
  padding-right: 1.2rem;
  border-bottom: 1px solid #eee;
  color: #111;
  width: 7rem;
}
</style>
"""


def _strip_html_tags(text: str) -> str:
    """Remove HTML tags and decode common entities for plain-text captions."""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>') \
               .replace('&nbsp;', '\u00a0').replace('&#8203;', '').strip()
    return text


def inject_figure_index(html: str) -> str:
    """Scan all <figcaption> elements and build a List-of-Figures table.

    The table is injected immediately after the opening of
    <main … id="quarto-document-content">, or just before the first <section>
    if the main tag is absent.

    Returns the modified HTML string.
    """
    # Collect captions
    captions = []
    for match in _FIGCAPTION_RE.finditer(html):
        raw = match.group(1)
        text = _strip_html_tags(raw).strip()
        if text:
            captions.append(text)

    if not captions:
        return html  # Nothing to index

    rows = ""
    for i, caption in enumerate(captions, start=1):
        rows += f'<tr><td>Figure&nbsp;{i}</td><td>{caption}</td></tr>\n'

    index_html = (
        _FIGURE_INDEX_STYLE
        + '\n<section class="fourd-figure-index" id="list-of-figures">\n'
        + '<h2>List of Figures</h2>\n'
        + '<table><tbody>\n'
        + rows
        + '</tbody></table>\n'
        + '</section>\n'
    )

    # Try to inject after <main … id="quarto-document-content">
    main_pattern = re.compile(
        r'(<main[^>]*id="quarto-document-content"[^>]*>)',
        re.IGNORECASE,
    )
    m = main_pattern.search(html)
    if m:
        pos = m.end()
        return html[:pos] + '\n' + index_html + html[pos:]

    # Fallback: inject before the first <section>
    section_pattern = re.compile(r'<section\b', re.IGNORECASE)
    m2 = section_pattern.search(html)
    if m2:
        pos = m2.start()
        return html[:pos] + index_html + html[pos:]

    # Last resort: append before </body>
    return html.replace('</body>', index_html + '</body>', 1)


# ---------------------------------------------------------------------------
# Template Application
# ---------------------------------------------------------------------------

_STYLE_INJECTION_COMMENT = '<!-- fourd-template-css -->'


def apply_template(
    html: str,
    *,
    template: str = "academic",
    custom_css: Optional[str] = None,
    add_index: bool = False,
) -> str:
    """Apply a named template (and optional custom CSS) to an export HTML document.

    Parameters
    ----------
    html : str
        Full rendered HTML document (paperview or standalone).
    template : str
        One of: 'academic', 'modern', 'compact', 'preprint', 'custom'.
    custom_css : str | None
        When ``template == 'custom'`` (or always), additional CSS injected
        after the preset. When ``template == 'custom'`` and ``custom_css``
        is not provided, the default custom starter is used.
    add_index : bool
        When True, inject a List-of-Figures table at the top of the document.

    Returns
    -------
    str
        Modified HTML string.
    """
    # Resolve CSS
    preset_css = TEMPLATES.get(template, TEMPLATES["academic"])

    parts = [f'<style id="fourd-template-preset">\n{preset_css}\n</style>']

    if custom_css and custom_css.strip():
        parts.append(f'<style id="fourd-template-custom">\n{custom_css}\n</style>')

    injected_css = '\n'.join(parts)

    # Try to inject just before </head>
    if '</head>' in html:
        html = html.replace('</head>', injected_css + '\n</head>', 1)
    else:
        # Prepend to body as fallback
        html = injected_css + '\n' + html

    # Optionally inject figure index
    if add_index:
        html = inject_figure_index(html)

    return html


# ---------------------------------------------------------------------------
# Quick sanity test (run directly: python export_templates.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    sample = """\
<html><head><title>Test</title></head>
<body>
<main class="content" id="quarto-document-content">
<section id="intro"><h2>Intro</h2><p>Hello world.</p>
<figure class="fourd-figure"><iframe></iframe>
<figcaption>Velocity field at t=0.5 s.</figcaption>
</figure>
<figure><img src="fig.png"><figcaption>Pressure distribution overview.</figcaption></figure>
</section>
</main>
</body></html>"""

    result = apply_template(sample, template="modern", add_index=True)
    print("--- modern + index ---")
    print(result[:2000])
    print("… OK")
