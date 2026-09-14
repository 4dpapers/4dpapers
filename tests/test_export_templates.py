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


REMOTE_URL_RE = re.compile(r"url\(\s*[\"']?(https?://[^\"')]+)", re.IGNORECASE)


@pytest.mark.parametrize("name", ["academic", "modern", "compact", "preprint"])
def test_template_contains_no_remote_urls(name):
    """Offline export must not reach the network.

    dashboard/compile_plugin.py rejects remote subresources during offline
    PDF export, so a remote @import here breaks that path outright.
    """
    mod = _load()
    css = mod.TEMPLATES[name]
    found = REMOTE_URL_RE.findall(css)
    assert not found, f"template {name!r} references remote resources: {found}"


def test_apply_template_injects_preset_before_head_close():
    mod = _load()
    html = "<html><head><title>t</title></head><body><p>x</p></body></html>"
    out = mod.apply_template(html, template="academic")
    assert 'id="fourd-template-preset"' in out
    assert out.index('id="fourd-template-preset"') < out.index("</head>")


def test_apply_template_falls_back_to_academic_for_unknown_name():
    mod = _load()
    html = "<html><head></head><body></body></html>"
    out = mod.apply_template(html, template="no-such-template")
    assert mod.TEMPLATES["academic"] in out


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
