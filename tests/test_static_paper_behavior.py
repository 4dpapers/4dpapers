"""Static papers must not call authoring-only persistence APIs."""
from pathlib import Path


ROOT = Path(__file__).parent.parent


def test_inline_relay_disables_persistence_outside_output_route():
    lua = (ROOT / "_extensions" / "4dpaper" / "shortcodes.lua").read_text(
        encoding="utf-8"
    )

    assert "var _CAN_PERSIST = /(^|\\/)output\\//" in lua
    assert "if (_CAN_PERSIST) return fetch(url, options);" in lua
    assert "if(_persist){fetch(\"/camera-lock/\"+PID)" in lua
    assert "if(_persist)fetch(\"/camera-lock/\"+PID" in lua


def test_asset_relay_matches_static_persistence_policy():
    relay = (ROOT / "_extensions" / "4dpaper" / "assets" / "relay.js").read_text(
        encoding="utf-8"
    )

    assert "var _CAN_PERSIST = /(^|\\/)output\\//" in relay
    assert "if (_CAN_PERSIST) return fetch(url, options);" in relay
    assert "_persist('/camera/'+camId" in relay
    assert "_persist('/field/'+figId2" in relay


def test_pdf_inline_code_filter_registered():
    extension = (ROOT / "_extensions" / "4dpaper" / "_extension.yml").read_text(
        encoding="utf-8"
    )
    lua = (ROOT / "_extensions" / "4dpaper" / "breakable-code.lua").read_text(
        encoding="utf-8"
    )

    assert "filters:" in extension
    assert "- breakable-code.lua" in extension
    assert 'FORMAT:match("latex")' in lua
    assert "\\allowbreak{}" in lua
    assert "\\texttt{" in lua
