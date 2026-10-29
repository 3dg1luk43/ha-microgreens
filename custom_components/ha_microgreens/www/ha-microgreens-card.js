// Microgreens - Home Assistant integration for planning and tracking microgreen trays.
// Copyright (C) 2026 Lukas Bandura
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// ha-microgreens-card.js - the Lovelace card <ha-microgreens-card> and its editor.
//
// Loaded on every dashboard as a frontend extra module (frontend.py), so there
// is no Lovelace resource to add. One card, four views:
//
//   type: custom:ha-microgreens-card
//   view: board | tasks | timeline | plot
//   plots: [A1, A2]      # board / tasks / timeline: only these plots
//   plot_id: A1          # plot view
//   title: My trays
//   days: 14             # timeline length
//   show_tasks: true     # board: today's tasks above the tiles
//   compact: false       # board / plot: smaller tiles, icon-only buttons
//
// 0.1.x dashboards keep working: custom:microgreens-card is the board view and
// custom:microgreens-plot-card (plot_id, title, compact) the plot view.

const V = (() => {
  try { return new URL(import.meta.url).searchParams.get('v') || ''; } catch (_) { return ''; }
})();
let STYLES, PANEL_PATH, esc, icon, loadI18n, hassLang, subscribe, plotTile, taskList, timeline, handleAction, addDays, errorText;
const coreReady = import(`./ha-microgreens-core.js${V ? `?v=${encodeURIComponent(V)}` : ''}`).then((core) => {
  ({ STYLES, PANEL_PATH, esc, icon, loadI18n, hassLang, subscribe, plotTile, taskList, timeline, handleAction, addDays, errorText } = core);
  return core;
});

// HA may create the element before this module has run (it loads the module
// with a script tag); a property set then shadows the setter. Re-apply it.
function upgradeProperties(el, names) {
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(el, name)) {
      const value = el[name];
      delete el[name];
      el[name] = value;
    }
  }
}

const VIEWS = ['board', 'tasks', 'timeline', 'plot'];

const CARD_STYLES = `
:host{display:block}
ha-card{overflow:hidden;height:100%}
.mg-card-head{display:flex;align-items:center;gap:8px;padding:14px 16px 0}
.mg-card-head h2{flex:1;margin:0;font-size:var(--ha-card-header-font-size,20px);font-weight:400;display:flex;align-items:center;gap:8px}
.mg-card-head a{color:var(--secondary-text-color);display:inline-flex}
.mg-card-body{padding:12px 16px 16px}
.mg-card-body .mg-tiles{grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}
:host([compact]) .mg-card-body .mg-tiles{grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:8px}
:host([compact]) .mg-tile{padding:10px}
.mg-card-tasks{margin-bottom:12px}
.mg-tile.single{border:none;padding:0;border-left:none;background:transparent}
.mg-msg{padding:16px;color:var(--secondary-text-color);display:flex;gap:8px;align-items:center}
.mg-tl{--mg-plot-w:84px}
`;

class HaMicrogreensCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.ctx = { host: this, hass: () => this._hass, i18n: null, snap: () => this._snap };
  }

  static getConfigElement() {
    return document.createElement('ha-microgreens-card-editor');
  }

  static getStubConfig() {
    return { view: 'board' };
  }

  setConfig(config) {
    if (!config || typeof config !== 'object') throw new Error('Invalid configuration');
    const view = config.view || 'board';
    if (!VIEWS.includes(view)) throw new Error(`view must be one of ${VIEWS.join(', ')}`);
    if (view === 'plot' && !config.plot_id) throw new Error('plot_id is required for view: plot');
    this._config = { ...config, view };
    this.toggleAttribute('compact', !!config.compact);
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || (this._i18n && this._i18n.lang !== hassLang(hass))) this._boot();
  }

  connectedCallback() {
    upgradeProperties(this, ['hass']);
    if (this._hass && this._i18n && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  async _boot() {
    await coreReady;
    this._i18n = await loadI18n(this._hass);
    this.ctx.i18n = this._i18n;
    if (!this._unsub && this.isConnected) this._subscribe();
    this._render();
  }

  _subscribe() {
    this._unsub = subscribe(this._hass, (snap, err) => {
      this._snap = snap;
      this._err = err;
      this._render();
    });
  }

  getCardSize() {
    const v = this._config && this._config.view;
    if (v === 'plot') return 3;
    if (v === 'tasks') return 3;
    if (v === 'timeline') return 5;
    return 6;
  }

  getGridOptions() {
    const v = this._config && this._config.view;
    if (v === 'plot') return { columns: 6, min_columns: 4, rows: 'auto' };
    if (v === 'tasks') return { columns: 6, min_columns: 4, rows: 'auto' };
    return { columns: 12, min_columns: 6, rows: 'auto' };
  }

  _plotsFilter(snap) {
    const wanted = Array.isArray(this._config.plots) && this._config.plots.length ? this._config.plots.map(String) : null;
    return wanted ? snap.plots.filter((p) => wanted.includes(p.id)) : snap.plots;
  }

  _render() {
    if (!this._config || !STYLES) return;
    const t = this._i18n;
    if (!this._root) {
      this.shadowRoot.innerHTML = `<style>${STYLES}${CARD_STYLES}</style><ha-card></ha-card>`;
      this._root = this.shadowRoot.querySelector('ha-card');
      this._root.addEventListener('click', (e) => {
        const el = e.target.closest('[data-act]');
        if (!el || !el.dataset.act || !this._snap || !this._snap.loaded) return;
        if (el.dataset.act === 'tl-sow') return this._timelineSow(e, el);
        handleAction(this.ctx, el);
      });
    }
    if (!t) { this._root.innerHTML = '<div class="mg-msg"></div>'; return; }
    const c = this._config;
    const title = c.title != null ? c.title : (c.view === 'plot' ? '' : t.tt(`card.title_${c.view}`));
    const head = title || c.view !== 'plot'
      ? `<div class="mg-card-head"><h2>${icon('mdi:sprout')}${esc(title)}</h2><a href="${PANEL_PATH}" title="${t.t('card.open_panel')}" aria-label="${t.t('card.open_panel')}">${icon('mdi:open-in-new')}</a></div>`
      : '';
    let body;
    if (this._err) body = `<div class="mg-msg">${icon('mdi:alert-circle-outline')}${esc(errorText(t, this._err))}</div>`;
    else if (!this._snap) body = `<div class="mg-msg">${t.t('panel.loading')}</div>`;
    else if (!this._snap.loaded) body = `<div class="mg-msg">${icon('mdi:power-plug-off-outline')}${t.t('panel.not_loaded')}</div>`;
    else body = this._view();
    this._root.innerHTML = `${head}<div class="mg-card-body">${body}</div>`;
  }

  _view() {
    const t = this._i18n;
    const snap = this._snap;
    const c = this._config;
    const plots = this._plotsFilter(snap);
    const ids = plots.map((p) => p.id);
    if (c.view === 'plot') {
      const plot = snap.plotById.get(String(c.plot_id));
      if (!plot) return `<div class="mg-msg">${t.t('card.unknown_plot', { plot: c.plot_id })}</div>`;
      return plotTile(t, snap, plot, { compact: c.compact }).replace('class="mg-tile ', 'class="mg-tile single ');
    }
    if (c.view === 'tasks') return taskList(t, snap, { plots: c.plots && c.plots.length ? ids : null });
    if (c.view === 'timeline') {
      const days = Math.max(7, Math.min(56, Number(c.days) || 14));
      const start = addDays(snap.today, -Math.round(days / 5));
      return timeline(t, { ...snap, plots }, { start, days });
    }
    const tasks = c.show_tasks === false ? '' : `<div class="mg-card-tasks">${taskList(t, snap, { plots: c.plots && c.plots.length ? ids : null })}</div>`;
    return `${tasks}<div class="mg-tiles">${plots.map((p) => plotTile(t, snap, p, { compact: c.compact })).join('')}</div>`;
  }

  _timelineSow(e, track) {
    const c = this._config;
    const days = Math.max(7, Math.min(56, Number(c.days) || 14));
    const start = addDays(this._snap.today, -Math.round(days / 5));
    const rect = track.getBoundingClientRect();
    const idx = Math.floor(((e.clientX - rect.left) / rect.width) * days);
    const date = addDays(start, Math.max(0, Math.min(days - 1, idx)));
    handleAction(this.ctx, { dataset: { act: 'sow', plot: track.dataset.plot, date: date < this._snap.today ? this._snap.today : date } });
  }
}

// --------------------------------------------------------------------------
// Visual editor (ha-form, which the dashboard editor has always loaded)
// --------------------------------------------------------------------------

class HaMicrogreensCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { view: 'board', ...config };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._form) this._form.hass = hass;
    if (first) {
      coreReady.then(async () => {
        this._i18n = await loadI18n(hass);
        this._unsub = subscribe(hass, (snap) => { this._snap = snap; this._render(); });
        this._render();
      });
    }
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  _schema() {
    const t = this._i18n;
    const plots = this._snap && this._snap.loaded ? this._snap.plots.map((p) => ({ value: p.id, label: p.name })) : [];
    const view = this._config.view;
    const schema = [
      { name: 'view', required: true, selector: { select: { mode: 'dropdown', options: VIEWS.map((v) => ({ value: v, label: t.tt(`card.view_${v}`) })) } } },
      { name: 'title', selector: { text: {} } },
    ];
    if (view === 'plot') {
      schema.push({ name: 'plot_id', required: true, selector: { select: { mode: 'dropdown', options: plots } } });
    } else {
      schema.push({ name: 'plots', selector: { select: { multiple: true, mode: 'list', options: plots } } });
    }
    if (view === 'timeline') schema.push({ name: 'days', selector: { number: { min: 7, max: 56, step: 7, mode: 'slider' } } });
    if (view === 'board') schema.push({ name: 'show_tasks', selector: { boolean: {} } });
    if (view === 'board' || view === 'plot') schema.push({ name: 'compact', selector: { boolean: {} } });
    return schema;
  }

  _render() {
    if (!this._config || !this._i18n || !this._hass) return;
    const t = this._i18n;
    if (!this._form) {
      this._form = document.createElement('ha-form');
      this._form.computeLabel = (s) => t.tt(`card.field_${s.name}`);
      this._form.computeHelper = (s) => (t.has(`card.help_${s.name}`) ? t.tt(`card.help_${s.name}`) : undefined);
      this._form.addEventListener('value-changed', (e) => {
        const value = { ...e.detail.value };
        for (const k of Object.keys(value)) {
          if (value[k] === '' || value[k] == null || (Array.isArray(value[k]) && !value[k].length)) delete value[k];
        }
        if (value.view !== 'plot') delete value.plot_id;
        else delete value.plots;
        this._config = value;
        this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: value }, bubbles: true, composed: true }));
        this._render();
      });
      this.appendChild(this._form);
    }
    this._form.hass = this._hass;
    this._form.data = { show_tasks: true, compact: false, days: 14, ...this._config };
    this._form.schema = this._schema();
  }
}

// --------------------------------------------------------------------------
// Registration, plus the 0.1.x card names
// --------------------------------------------------------------------------

class LegacyBoardCard extends HaMicrogreensCard {
  setConfig(config) { super.setConfig({ ...config, type: 'custom:ha-microgreens-card', view: 'board' }); }
}

class LegacyPlotCard extends HaMicrogreensCard {
  setConfig(config) { super.setConfig({ ...config, type: 'custom:ha-microgreens-card', view: 'plot' }); }
}

const define = (tag, cls) => { if (!customElements.get(tag)) customElements.define(tag, cls); };
define('ha-microgreens-card', HaMicrogreensCard);
define('ha-microgreens-card-editor', HaMicrogreensCardEditor);
define('microgreens-card', LegacyBoardCard);
define('microgreens-plot-card', LegacyPlotCard);

// The card picker reads this list when it opens; HA sets <html lang> to the
// user's language long before that.
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === 'ha-microgreens-card')) {
  const entry = { type: 'ha-microgreens-card', name: 'Microgreens', description: '', preview: true, documentationURL: 'https://github.com/3dg1luk43/ha-microgreens' };
  window.customCards.push(entry);
  coreReady.then(() => loadI18n({ language: document.documentElement.lang || 'en' })).then((i18n) => { entry.description = i18n.tt('card.picker_description'); });
}
