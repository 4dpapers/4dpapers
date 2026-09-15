"""Tests for panel camera sync mode."""
from __future__ import annotations

from pathlib import Path


class TestParsePanelShortcodes:
    def test_camera_mode_defaults_to_independent(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-panel id="p1" layout="2x1" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "independent"

    def test_camera_mode_sync_parsed(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-panel id="p1" layout="2x1" camera="sync" src1="a.foam" id1="f1" field1="Vm" src2="b.foam" id2="f2" field2="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert result[0]["camera_mode"] == "sync"

    def test_unknown_camera_value_treated_as_independent(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-panel id="p1" layout="1x1" camera="wibble" src1="a.foam" id1="f1" field1="Vm" >}}'
        result = mod.parse_panel_shortcodes(text)
        assert "camera_mode" in result[0]


class TestParseGraphPanelShortcodes:
    def test_graph_panel_collects_separate_json_subfigures(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = (
            '{{< 4d-graph-panel id="gp" layout="2x2" '
            'src1="a.json" id1="ga" src2="b.json" id2="gb" >}}'
        )
        result = mod.parse_graph_panel_shortcodes(text)
        assert result[0]["id"] == "gp"
        assert result[0]["layout"] == "2x2"
        assert result[0]["subfigures"] == [
            {"src": "a.json", "id": "ga", "caption": ""},
            {"src": "b.json", "id": "gb", "caption": ""},
        ]

    def test_graph_panel_defaults_subfigure_ids(self, fourdpaper_hook):
        mod = fourdpaper_hook
        text = '{{< 4d-graph-panel id="gp" src1="a.json" src2="b.json" >}}'
        result = mod.parse_graph_panel_shortcodes(text)
        assert [sub["id"] for sub in result[0]["subfigures"]] == ["gp-1", "gp-2"]


class TestGeneratePanelHtml:
    def test_sync_re_relay_contains_panel_id(self, tmp_path, fourdpaper_hook):
        """Sync composite HTML must contain PANEL_ID variable."""
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_html)
        assert "camera_mode" in source
        assert "PANEL_ID" in source

    def test_sync_re_relay_contains_camera_apply_broadcast(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-camera-apply" in source

    def test_independent_re_relay_has_lock_passthrough(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_html)
        assert "4dpaper-lock-query" in source
        assert "4dpaper-lock-state" in source


class TestGeneratePngFigureCameraFigId:
    def test_camera_fig_id_param_exists(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        sig = inspect.signature(mod.generate_png_figure)
        assert "camera_fig_id" in sig.parameters
        assert sig.parameters["camera_fig_id"].default is None

    def test_camera_fig_id_used_in_lookup(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_png_figure)
        assert "camera_fig_id" in source
        assert "_cam_id" in source


class TestGenerateHtmlFigureCameraFigId:
    def test_camera_fig_id_param_exists(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        sig = inspect.signature(mod.generate_html_figure)
        assert "camera_fig_id" in sig.parameters
        assert sig.parameters["camera_fig_id"].default is None

    def test_camera_fig_id_used_in_lookup(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_html_figure)
        assert "camera_fig_id" in source
        assert "_cam_id" in source


class TestGeneratePanelPngSyncCamera:
    def test_sync_mode_uses_panel_id_for_camera(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_png)
        assert "camera_mode" in source
        assert "camera_fig_id" in source

    def test_panel_png_reads_saved_field_state(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_png)
        assert "_load_saved_field_state" in source


class TestSyncPanelCacheInvalidation:
    def test_main_source_uses_panel_camera_for_sync(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.main)
        assert "camera_mode" in source
        assert "shared_cam" in source

    def test_main_source_tracks_panel_field_state(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.main)
        assert 'field_{sub[\'id\']}.json' in source

    def test_main_source_collects_includes_from_all_top_level_qmds(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.main)
        assert "root_qmds = preferred_roots or sorted(project_dir.glob(\"*.qmd\"))" in source
        assert "qmd_files.extend(collect_includes(root_qmd, seen_qmds))" in source


class TestGeneratePanelHtmlWritesManifest:
    def test_generate_panel_html_source_writes_manifest(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_html)
        assert "manifest" in source
        assert ".manifest.json" in source

    def test_relay_script_handles_panel_sync(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'data-panel' in content
        assert 'querySelectorAll' in content

    def test_generate_panel_html_uses_saved_field_state_and_shared_camera(self, fourdpaper_hook):
        import inspect
        mod = fourdpaper_hook
        source = inspect.getsource(mod.generate_panel_html)
        assert "_load_saved_field_state" in source
        assert "camera_fig_id" in source


class TestFourdPanelLua:
    def test_fourd_panel_reads_camera_kwarg(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'kwargs["camera"]' in content

    def test_fourd_panel_has_sync_branch(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'camera_mode == "sync"' in content

    def test_fourd_panel_sync_uses_direct_srcdoc_iframes(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'data-panel="' in content
        assert '"id" .. n' in content


class TestIframeSizingLua:
    def test_shortcodes_derives_iframe_height_from_rendered_figure(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "local function _figure_html_height" in content
        assert "height:%s*(%d+%.?%d*)px" in content
        assert '_iframe_height(id, height, "600px")' in content

    def test_shortcodes_versions_app_mode_state_figure_iframes(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert "local function _state_figure_url" in content
        assert "?v=" in content
        assert "'<iframe src=\"' .. _state_figure_url" in content

    def test_shortcodes_has_static_subimage_grid(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '["4d-subimages"]' in content
        assert "fourd-subfigure-grid" in content
        assert "grid-template-columns:repeat(" in content
        assert "height:auto" in content

    def test_shortcodes_has_graph_panel_grid(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert '["4d-graph-panel"]' in content
        assert "fourd_graph_panel" in content
        assert "_state_figure_url(item.id, \".html\")" in content

    def test_graph_panel_latex_avoids_nested_figure_without_caption_attr(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        graph_panel = content.split("local function fourd_graph_panel", 1)[1].split("return {", 1)[0]
        assert "local lines = {}" in graph_panel
        assert 'if caption ~= "" then\n      table.insert(lines, "\\\\begin{figure}[h]\\n\\\\centering\\n")' in graph_panel

    def test_export_template_caps_figures_to_text_width(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "export_templates.py").read_text()
        assert "_RESPONSIVE_FIGURE_CSS" in content
        assert "figure, .quarto-figure, .fourd-figure" in content
        assert "max-width: 100% !important" in content
        assert ".fourd-subfigure-grid" in content

    def test_paperview_css_caps_pdf_figures_to_text_width(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "paperview.css").read_text()
        assert "@media print" in content
        assert "@page" in content
        assert "figure, .fourd-figure" in content
        assert ".fourd-subfigure-grid" in content
        assert "max-width: 100% !important" in content


class TestPanelLockToolbar:
    def test_shortcodes_lua_contains_panel_lock_toolbar(self):
        """shortcodes.lua must contain the panel-level lock bar markup."""
        lua_src = (
            Path(__file__).parent.parent
            / "_extensions" / "4dpaper" / "shortcodes.lua"
        ).read_text()
        assert "plb-btn-" in lua_src
        assert "4dpaper-lock-all" in lua_src
        assert "4dpaper-hide-lock-btn" in lua_src


class TestTimeseriesTimeSyncRelay:
    """Regression tests: sync re-relay must forward 4dpaper-time to siblings."""

    def test_sync_re_relay_handles_time_message(self):
        """The sync composite re-relay script must relay '4dpaper-time' messages."""
        import inspect
        from fourdpaper.lib import render
        source = inspect.getsource(render._panel_transport_html)
        assert "4dpaper-time" in source, (
            "generate_panel_html sync re-relay must handle '4dpaper-time' "
            "so timeseries subfigures stay in step"
        )

    def test_sync_re_relay_sends_time_apply(self):
        """When '4dpaper-time' arrives the relay must fan out '4dpaper-time-apply'."""
        import inspect
        from fourdpaper.lib import render
        source = inspect.getsource(render._panel_transport_html)
        assert "4dpaper-time-apply" in source, (
            "The re-relay must broadcast '4dpaper-time-apply' to sibling iframes"
        )

    def test_sync_re_relay_skips_sender_for_time(self):
        """The time relay must skip the source iframe to avoid feedback loops."""
        import inspect
        from fourdpaper.lib import render
        source = inspect.getsource(render._panel_transport_html)
        assert "source_idx" in source, (
            "Time relay should track the sending iframe (source_idx) to skip it"
        )


class TestStandaloneRelay:
    def test_shortcodes_relay_handles_time_message(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'e.data.type==="4dpaper-time"' in content

    def test_shortcodes_relay_limits_time_broadcast_to_opted_in_iframes(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'data-panel-time-sync' in content
        assert 'timeSyncEnabled' in content

    def test_shortcodes_relay_broadcasts_time_apply(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'type:"4dpaper-time-apply"' in content

    def test_shortcodes_relay_skips_time_sender(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        assert 'contentWindow!==e.source' in content

    def test_shortcodes_relay_applies_camera_before_fetch_ack(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        camera_idx = content.index('} else if(e.data.type==="4dpaper-camera"){')
        apply_idx = content.index("liveFrames[_pl].contentWindow.postMessage({type:'4dpaper-camera-apply',camera:e.data.camera},'*');", camera_idx)
        fetch_idx = content.index("_persist('/camera/'+camId,{", camera_idx)
        assert apply_idx < fetch_idx


class TestSyncPanelTimeControls:
    def test_sync_panel_iframes_do_not_opt_into_child_time_broadcast(self):
        content = (Path(__file__).parent.parent / "_extensions" / "4dpaper" / "shortcodes.lua").read_text()
        sync_branch = content.split('if camera_mode == "sync" then', 1)[1].split('-- Independent mode', 1)[0]
        assert 'data-panel-time-sync="true"' not in sync_branch
