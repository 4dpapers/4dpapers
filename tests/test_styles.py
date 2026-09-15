"""Tests for figure style template loading and resolution."""
from __future__ import annotations


class TestLoadStyles:
    def test_missing_file_returns_empty_dict(self, tmp_path, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.load_styles(tmp_path / "nonexistent.yml")
        assert result == {}

    def test_malformed_yaml_returns_empty_dict(self, tmp_path, fourdpaper_hook):
        bad = tmp_path / "styles.yml"
        bad.write_text(": bad: yaml: [[[")
        mod = fourdpaper_hook
        result = mod.load_styles(bad)
        assert result == {}

    def test_valid_file_parses_correctly(self, tmp_path, fourdpaper_hook):
        yml = tmp_path / "styles.yml"
        yml.write_text("""
defaults:
  background: "white"
  axis_color: "black"
  cmap: "coolwarm"
styles:
  vm-dark:
    background: "#1a1a2e"
    axis_color: "white"
    fields:
      Vm: viridis
""")
        mod = fourdpaper_hook
        result = mod.load_styles(yml)
        assert result["defaults"]["background"] == "white"
        assert result["styles"]["vm-dark"]["background"] == "#1a1a2e"
        assert result["styles"]["vm-dark"]["fields"]["Vm"] == "viridis"


class TestResolveStyle:
    def _config(self):
        return {
            "defaults": {"background": "white", "axis_color": "black", "cmap": "coolwarm"},
            "styles": {
                "vm-dark": {
                    "background": "#1a1a2e",
                    "axis_color": "white",
                    "fields": {"Vm": "viridis", "activationTime": "plasma"},
                },
                "no-fields": {
                    "background": "#222",
                    "axis_color": "gray",
                    "cmap": "jet",
                },
            },
        }

    def test_per_field_cmap_wins(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["cmap"] == "viridis"

    def test_style_cmap_fallback_when_field_not_listed(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "no-fields", "Vm")
        assert result["cmap"] == "jet"

    def test_defaults_cmap_when_no_style(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "", "Vm")
        assert result["cmap"] == "coolwarm"

    def test_background_from_named_style(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["background"] == "#1a1a2e"

    def test_axis_color_from_named_style(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "vm-dark", "Vm")
        assert result["axis_color"] == "white"

    def test_defaults_used_when_style_name_empty(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "", "Vm")
        assert result["background"] == "white"
        assert result["axis_color"] == "black"

    def test_unknown_style_name_falls_back_to_defaults(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style(self._config(), "nonexistent", "Vm")
        assert result["cmap"] == "coolwarm"
        assert result["background"] == "white"

    def test_empty_config_returns_hard_defaults(self, fourdpaper_hook):
        mod = fourdpaper_hook
        result = mod.resolve_style({}, "", "Vm")
        assert result == {"background": "white", "axis_color": "black", "cmap": "coolwarm"}

    def test_transparent_background_normalised_to_white(self, fourdpaper_hook):
        mod = fourdpaper_hook
        config = {"defaults": {"background": "transparent", "axis_color": "black", "cmap": "coolwarm"}, "styles": {}}
        result = mod.resolve_style(config, "", "Vm")
        assert result["background"] == "white"


class TestParseShortcodesStyle:
    def test_style_param_parsed(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-image src="case.foam" id="fig-vm" field="Vm" style="vm-dark" >}}'
        result = mod.parse_shortcodes(text)
        assert len(result) == 1
        assert result[0]["style"] == "vm-dark"

    def test_style_defaults_to_empty_string(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-image src="case.foam" id="fig-vm" field="Vm" >}}'
        result = mod.parse_shortcodes(text)
        assert result[0]["style"] == ""

    def test_style_key_always_present(self, fourdpaper_hook):
        """Parsed shortcode dicts always include `style`."""
        mod = fourdpaper_hook
        text = '{{< 4d-image src="case.foam" id="fig-vm" >}}'
        result = mod.parse_shortcodes(text)
        assert "style" in result[0]


class TestGeneratorsAcceptStyleParams:
    def test_generate_png_figure_accepts_style_params(self, fourdpaper_hook):
        """`generate_png_figure` accepts style parameters."""
        import inspect
        mod = fourdpaper_hook
        sig = inspect.signature(mod.generate_png_figure)
        params = sig.parameters
        assert "background" in params
        assert "axis_color" in params
        assert "cmap" in params
        assert params["background"].default == "white"
        assert params["axis_color"].default == "black"
        assert params["cmap"].default == "coolwarm"

    def test_generate_html_figure_accepts_style_params(self, fourdpaper_hook):
        """`generate_html_figure` accepts style parameters."""
        import inspect
        mod = fourdpaper_hook
        sig = inspect.signature(mod.generate_html_figure)
        params = sig.parameters
        assert "background" in params
        assert "axis_color" in params
        assert "cmap" in params
        assert params["background"].default == "white"
        assert params["axis_color"].default == "black"
        assert params["cmap"].default == "coolwarm"

    def test_generate_png_figure_hardcoded_values_replaced(self, fourdpaper_hook):
        """`generate_png_figure` does not hardcode style values."""
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_png_figure)
        assert "#1a1a2e" not in source, \
            "Hardcoded background '#1a1a2e' must be replaced with background param"
        assert 'cmap="coolwarm"' not in source, \
            "Hardcoded cmap='coolwarm' in add_mesh call must be replaced with cmap param"

    def test_generate_html_figure_hardcoded_values_replaced(self, fourdpaper_hook):
        """`generate_html_figure` does not hardcode style values."""
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_html_figure)
        assert "#1a1a2e" not in source, \
            "Hardcoded background '#1a1a2e' must be replaced with background param"
        assert 'cmap="coolwarm"' not in source, \
            "Hardcoded cmap='coolwarm' in add_mesh call must be replaced with cmap param"


class TestCacheInvalidationWithStyles:
    def test_styles_yml_change_triggers_regen(self, tmp_path, fourdpaper_hook):
        """A newer style file invalidates the cache."""
        import time
        mod = fourdpaper_hook

        styles_yml = tmp_path / "_4dpaper_styles.yml"
        src        = tmp_path / "case.foam"
        output     = tmp_path / "fig.html"

        styles_yml.write_text("defaults:\n  cmap: coolwarm\n")
        src.write_text("x")
        time.sleep(0.02)
        output.write_text("<html/>")
        time.sleep(0.02)
        styles_yml.touch()

        result = mod.is_cache_valid(output, src, extra_deps=[styles_yml])
        assert result is False

    def test_styles_yml_older_than_output_no_regen(self, tmp_path, fourdpaper_hook):
        import time
        mod = fourdpaper_hook

        styles_yml = tmp_path / "_4dpaper_styles.yml"
        src        = tmp_path / "case.foam"
        output     = tmp_path / "fig.html"

        styles_yml.write_text("defaults:\n  cmap: coolwarm\n")
        src.write_text("x")
        time.sleep(0.02)
        output.write_text("<html/>")

        result = mod.is_cache_valid(output, src, extra_deps=[styles_yml])
        assert result is True
