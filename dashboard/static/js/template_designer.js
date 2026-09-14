/**
 * 4Dpapers — HTML Export Template Settings
 *
 * Wires up the template controls inside the ⚙ Settings panel:
 *   - Preset buttons (Academic, Modern, Compact, Preprint, Custom)
 *   - "Add list of figures" toggle
 *   - Custom CSS textarea (visible only for 'Custom' preset)
 *
 * All choices are persisted to localStorage and reflected in
 * `state.templateSettings`, which the "Export to HTML" button reads.
 */

(function () {
  'use strict';

  const LS_PRESET     = '4dpapers_template_preset';
  const LS_INDEX      = '4dpapers_template_index';
  const LS_CUSTOM_CSS = '4dpapers_template_custom_css';

  const PRESETS = ['academic', 'modern', 'compact', 'preprint', 'custom'];

  function el(id) { return document.getElementById(id); }

  // ── Sync state.templateSettings (defined in index.html) ──────────────────

  function syncState(key, value) {
    if (typeof state !== 'undefined' && state.templateSettings) {
      state.templateSettings[key] = value;
    }
  }

  // ── Preset buttons ────────────────────────────────────────────────────────

  function buildPresetButtons() {
    const container = el('template-preset-btns');
    if (!container) return;

    const active = (typeof state !== 'undefined' && state.templateSettings?.preset)
      ? state.templateSettings.preset
      : (localStorage.getItem(LS_PRESET) || 'academic');

    container.innerHTML = '';

    PRESETS.forEach((name) => {
      const btn = document.createElement('button');
      btn.id    = `tmpl-preset-${name}`;
      btn.type  = 'button';
      btn.textContent = name.charAt(0).toUpperCase() + name.slice(1);
      applyPresetBtnStyle(btn, name === active);

      btn.addEventListener('click', () => selectPreset(name));
      container.appendChild(btn);
    });
  }

  function applyPresetBtnStyle(btn, isActive) {
    btn.style.cssText = [
      'padding: 4px 10px',
      'border-radius: 4px',
      'font-size: 11px',
      'font-weight: 500',
      'cursor: pointer',
      'transition: background 0.15s, color 0.15s, border-color 0.15s',
      isActive
        ? 'background: rgba(19,138,124,0.18); border: 1px solid #138a7c; color: #5eead4;'
        : 'background: transparent; border: 1px solid #2A3047; color: #9CA3AF;',
    ].join(';');
  }

  function selectPreset(name) {
    // Update buttons
    PRESETS.forEach((p) => {
      const b = el(`tmpl-preset-${p}`);
      if (b) applyPresetBtnStyle(b, p === name);
    });

    // Show/hide custom CSS block
    const wrap = el('templateCustomCSSWrap');
    if (wrap) wrap.style.display = name === 'custom' ? 'block' : 'none';

    // Persist
    localStorage.setItem(LS_PRESET, name);
    syncState('preset', name);
  }

  // ── "Add list of figures" toggle ─────────────────────────────────────────

  function wireIndexToggle() {
    const checkbox = el('templateAddIndex');
    const track    = el('templateAddIndexTrack');
    const thumb    = el('templateAddIndexThumb');
    if (!checkbox) return;

    // Restore saved value
    const saved = localStorage.getItem(LS_INDEX) === 'true';
    checkbox.checked = saved;
    applyToggleStyle(track, thumb, saved);
    syncState('addIndex', saved);

    checkbox.addEventListener('change', () => {
      const checked = checkbox.checked;
      applyToggleStyle(track, thumb, checked);
      localStorage.setItem(LS_INDEX, String(checked));
      syncState('addIndex', checked);
    });
  }

  function applyToggleStyle(track, thumb, on) {
    if (!track || !thumb) return;
    track.style.background = on ? '#138a7c' : '#2A3047';
    thumb.style.transform  = on ? 'translateX(15px)' : 'translateX(0)';
  }

  // ── Custom CSS textarea ───────────────────────────────────────────────────

  function wireCustomCSS() {
    const textarea = el('templateCustomCSS');
    if (!textarea) return;

    // Restore saved value
    const saved = localStorage.getItem(LS_CUSTOM_CSS) || '';
    textarea.value = saved;
    syncState('customCSS', saved);

    let debounce;
    textarea.addEventListener('input', () => {
      clearTimeout(debounce);
      debounce = setTimeout(() => {
        const val = textarea.value;
        localStorage.setItem(LS_CUSTOM_CSS, val);
        syncState('customCSS', val);
      }, 400);
    });
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
      return;
    }

    // Defer slightly so index.html finishes setting up the DOM and `state`
    setTimeout(() => {
      buildPresetButtons();
      wireIndexToggle();
      wireCustomCSS();

      // Restore the custom CSS wrapper visibility if 'custom' was the saved preset
      const savedPreset = localStorage.getItem(LS_PRESET) || 'academic';
      if (savedPreset === 'custom') {
        const wrap = el('templateCustomCSSWrap');
        if (wrap) wrap.style.display = 'block';
      }
    }, 150);
  }

  init();

})();
