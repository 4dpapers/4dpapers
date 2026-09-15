"""Tests for the HTML export template engine."""
from __future__ import annotations

import importlib.util
import pathlib
import re

import pytest

_SRC = pathlib.Path("_extensions/4dpaper/export_templates.py")


def _load():
    """Load export_templates by path.

    The package is not importable as `_extensions.4dpaper.export_templates`
    because `4dpaper` begins with a digit. v1.1 PR 5 makes this unnecessary.
    """
    spec = importlib.util.spec_from_file_location("fourd_export_templates", _SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


REMOTE_RE = re.compile(r"https?://", re.IGNORECASE)


@pytest.mark.parametrize("name", ["academic", "modern", "compact", "preprint"])
def test_template_contains_no_remote_urls(name):
    """Offline export must not reach the network.

    dashboard/compile_plugin.py rejects remote subresources during offline
    PDF export, so any remote reference here breaks that path outright.
    Matches bare `@import "https://..."` as well as url()-wrapped forms.
    """
    mod = _load()
    css = mod.TEMPLATES[name]
    found = REMOTE_RE.findall(css)
    assert not found, f"template {name!r} references remote resources: {css[:400]}"


def test_remote_url_guard_detects_bare_css_import():
    """Guard the guard: a bare @import must be caught, not just url(...)."""
    assert REMOTE_RE.findall('@import "https://fonts.googleapis.com/css2?family=X";')
    assert REMOTE_RE.findall("@import url('https://fonts.googleapis.com/css2?family=X');")
    assert not REMOTE_RE.findall("src: url('CrimsonPro-400.woff2') format('woff2');")


def test_apply_template_injects_preset_before_head_close():
    mod = _load()
    html = "<html><head><title>t</title></head><body><p>x</p></body></html>"
    out = mod.apply_template(html, template="academic")
    assert 'id="fourd-template-preset"' in out
    assert out.index('id="fourd-template-preset"') < out.index("</head>")


def test_unknown_template_name_is_rejected():
    """Silent fallback hides a typo in a published document's styling."""
    mod = _load()
    with pytest.raises(ValueError, match="unknown template"):
        mod.apply_template("<html><head></head><body></body></html>",
                           template="no-such-template")


def test_custom_css_cannot_close_its_style_block():
    """The threat is closing <style> early, not the presence of text.

    Escaped markup left inside the element is inert CSS. What must never
    happen is the element terminating, which would make everything after
    it live markup in a document shared with reviewers.
    """
    mod = _load()
    out = mod.apply_template(
        "<html><head></head><body></body></html>",
        template="modern",
        custom_css="body{color:red}</style><script>alert(1)</script>",
    )
    custom_start = out.index('id="fourd-template-custom"')
    # The first `</style>` after the custom block opens must be the one
    # the template itself emits, not one smuggled in by the author.
    injected = out[custom_start:]
    assert "<\\/style" in injected, "the author's closing tag was not escaped"
    # And the document must not contain an unescaped author-supplied close
    # that precedes the template's own.
    assert injected.count("</style>") == 1, (
        "custom CSS closed the style block early"
    )


def test_apply_template_includes_custom_css_when_given():
    mod = _load()
    html = "<html><head></head><body></body></html>"
    out = mod.apply_template(html, template="modern", custom_css="body{color:red}")
    assert 'id="fourd-template-custom"' in out
    assert "body{color:red}" in out


def test_apply_template_omits_custom_block_when_css_blank():
    mod = _load()
    html = "<html><head></head><body></body></html>"
    out = mod.apply_template(html, template="modern", custom_css="   ")
    assert 'id="fourd-template-custom"' not in out


def test_inject_figure_index_lists_each_figcaption():
    mod = _load()
    html = (
        '<html><body><main id="quarto-document-content">'
        "<figure><figcaption>First figure</figcaption></figure>"
        "<figure><figcaption>Second figure</figcaption></figure>"
        "</main></body></html>"
    )
    out = mod.inject_figure_index(html)
    assert "First figure" in out
    assert "Second figure" in out
    assert out.count("<table") >= 1


def test_inject_figure_index_is_noop_without_figures():
    mod = _load()
    html = '<html><body><main id="quarto-document-content"><p>no figures</p></main></body></html>'
    out = mod.inject_figure_index(html)
    assert "<table" not in out


def test_strip_html_tags_decodes_entities():
    mod = _load()
    assert mod._strip_html_tags("<em>a</em> &amp; <b>b</b>") == "a & b"


def test_figure_index_escapes_caption_markup():
    """An entity-encoded tag in a caption must not become live markup."""
    mod = _load()
    html_doc = (
        '<html><body><main id="quarto-document-content">'
        "<figure><figcaption>Flow in &lt;script&gt;alert(1)&lt;/script&gt; region"
        "</figcaption></figure></main></body></html>"
    )
    out = mod.inject_figure_index(html_doc)
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out
