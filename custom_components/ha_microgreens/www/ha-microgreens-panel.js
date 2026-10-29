// Microgreens - Home Assistant integration for planning and tracking microgreen trays.
// Copyright (C) 2026 Lukas Bandura
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// ha-microgreens-panel.js - the sidebar panel <ha-microgreens-panel>.
//
// Push-driven: one WebSocket subscription (core.subscribe) delivers the whole
// snapshot after every change, and each push re-renders the open tab. Dialogs
// live outside the tab container, so a push never clobbers a form being typed in.

const V = (() => {
  try { return new URL(import.meta.url).searchParams.get('v') || ''; } catch (_) { return ''; }
})();
// The core is imported without top-level await, so the element below is
// defined the moment this module runs; methods wait for it in _boot().
let STYLES, PALETTE, esc, safeColor, icon, cropDot, statusPill, loadI18n, hassLang, subscribe, ws, errorText,
  addDays, daysBetween, fmtDate, plotTile, taskList, timeline, toast, openDialog, busy, readForm,
  stageFields, cropSummary, cropStats, handleAction, sowDialog;
const coreReady = import(`./ha-microgreens-core.js${V ? `?v=${encodeURIComponent(V)}` : ''}`).then((core) => {
  ({ STYLES, PALETTE, esc, safeColor, icon, cropDot, statusPill, loadI18n, hassLang, subscribe, ws, errorText,
  addDays, daysBetween, fmtDate, plotTile, taskList, timeline, toast, openDialog, busy, readForm,
  stageFields, cropSummary, cropStats, handleAction, sowDialog } = core);
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

const TABS = [
  { id: 'board', icon: 'mdi:view-grid-outline' },
  { id: 'timeline', icon: 'mdi:chart-timeline' },
  { id: 'crops', icon: 'mdi:sprout-outline' },
  { id: 'plots', icon: 'mdi:tray-full' },
  { id: 'history', icon: 'mdi:history' },
  { id: 'settings', icon: 'mdi:cog-outline', admin: true },
];
const RANGES = [14, 28, 56];
const LS = 'ha_microgreens.';

const PANEL_STYLES = `
:host{display:block;height:100vh;height:100dvh;overflow:hidden;background:var(--primary-background-color);color:var(--primary-text-color);font-family:var(--paper-font-body1_-_font-family,Roboto,sans-serif)}
.mg-app{display:flex;flex-direction:column;height:100%}
.mg-toolbar{display:flex;align-items:center;gap:8px;height:var(--header-height,56px);padding:0 12px 0 4px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff);flex:none}
.mg-toolbar ha-menu-button{color:inherit}
:host(:not([narrow])) .mg-toolbar ha-menu-button{display:none}
:host(:not([narrow])) .mg-toolbar{padding-left:20px}
.mg-brand{display:flex;align-items:center;gap:8px;font-size:20px;font-weight:400;flex:1;min-width:0}
.mg-brand .mg-ic{--mdc-icon-size:24px;width:24px;height:24px}
.mg-toolbar .mg-btn{background:rgba(255,255,255,.16);border-color:rgba(255,255,255,.3);color:inherit}
.mg-tabs{display:flex;gap:4px;padding:0 12px;background:var(--app-header-background-color,var(--primary-color));color:var(--app-header-text-color,#fff);overflow-x:auto;flex:none;scrollbar-width:none}
.mg-tab{display:inline-flex;align-items:center;gap:6px;padding:10px 14px 12px;border:none;background:none;color:inherit;opacity:.78;font:inherit;font-size:14px;font-weight:500;cursor:pointer;border-bottom:3px solid transparent;white-space:nowrap}
.mg-tab[aria-selected=true]{opacity:1;border-bottom-color:currentColor}
.mg-tab:focus-visible{outline:2px solid currentColor;outline-offset:-4px}
.mg-main{flex:1;overflow:auto;-webkit-overflow-scrolling:touch}
.mg-content{max-width:1400px;margin:0 auto;padding:16px 16px 96px}
:host([narrow]) .mg-content{padding:12px 10px 96px}
.mg-card{background:var(--card-background-color,#fff);border-radius:var(--mg-radius);border:1px solid var(--divider-color);padding:16px;box-shadow:var(--ha-card-box-shadow,none)}
.mg-card h3{margin:0 0 12px;font-size:16px;font-weight:600;display:flex;align-items:center;gap:8px}
.mg-section-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:4px 0 14px}
.mg-section-head h2{margin:0;font-size:20px;font-weight:500}
.mg-summary{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}
.mg-stat{display:flex;align-items:center;gap:10px;padding:10px 14px;border-radius:var(--mg-radius);background:var(--card-background-color,#fff);border:1px solid var(--divider-color);min-width:130px}
.mg-stat b{font-size:22px;font-weight:600;line-height:1}
.mg-stat span{font-size:12px;color:var(--secondary-text-color)}
.mg-stat .mg-ic{--mdc-icon-size:22px;width:22px;height:22px}
.mg-board{display:grid;grid-template-columns:minmax(280px,360px) 1fr;gap:16px;align-items:start}
.mg-board .mg-today-card{position:sticky;top:0}
@media (max-width:900px){.mg-board{grid-template-columns:1fr}.mg-board .mg-today-card{position:static}}
.mg-tl-tools{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.mg-tl-tools .mg-muted{margin-left:auto;font-size:12px}
.mg-seg-btns{display:inline-flex;border:1px solid var(--divider-color);border-radius:10px;overflow:hidden}
.mg-seg-btns button{border:none;background:transparent;color:var(--primary-text-color);padding:7px 12px;font:inherit;font-size:13px;cursor:pointer}
.mg-seg-btns button[aria-pressed=true]{background:var(--primary-color);color:var(--text-primary-color,#fff)}
.mg-crop-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.mg-crop{position:relative;padding:16px 16px 14px 20px;overflow:hidden}
.mg-crop::before{content:"";position:absolute;inset:0 auto 0 0;width:6px;background:var(--crop-color)}
.mg-crop-top{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.mg-crop-top b{font-size:16px}
.mg-crop-days{font-size:24px;font-weight:600;white-space:nowrap}
.mg-crop-days small{font-size:12px;color:var(--secondary-text-color);font-weight:400;margin-left:2px}
.mg-crop .mg-stagebar{margin:10px 0}
.mg-crop-stats{display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--secondary-text-color);margin-top:8px}
.mg-crop-stats span{display:inline-flex;align-items:center;gap:4px}
.mg-crop-stats .mg-ic{--mdc-icon-size:14px;width:14px;height:14px}
.mg-notes{font-size:12px;color:var(--secondary-text-color);margin-top:8px;white-space:pre-line;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.mg-table{width:100%;border-collapse:collapse;font-size:14px}
.mg-table th{text-align:left;font-size:12px;font-weight:600;color:var(--secondary-text-color);padding:8px 10px;border-bottom:1px solid var(--divider-color);white-space:nowrap}
.mg-table td{padding:9px 10px;border-bottom:1px solid var(--divider-color);vertical-align:middle}
.mg-table tr[data-act]{cursor:pointer}
.mg-table tr[data-act]:hover td{background:var(--secondary-background-color)}
.mg-table .num{text-align:right;font-variant-numeric:tabular-nums}
.mg-table-wrap{overflow-x:auto}
.mg-row-actions{display:flex;gap:4px;justify-content:flex-end}
.mg-filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.mg-filters select{font:inherit;font-size:13px;padding:7px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color)}
.mg-stack{display:flex;flex-direction:column;gap:16px}
.mg-switch{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid var(--divider-color)}
.mg-switch:last-child{border-bottom:none}
.mg-switch>div{display:flex;flex-direction:column;gap:2px}
.mg-switch small{color:var(--secondary-text-color);font-size:12px}
.mg-switch input[type=checkbox]{width:40px;height:22px;accent-color:var(--primary-color)}
.mg-switch input[type=time]{font:inherit;padding:6px 8px;border-radius:8px;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--primary-text-color)}
.mg-targets{display:flex;flex-direction:column;gap:6px;max-height:260px;overflow:auto;padding:4px 0}
.mg-targets label{display:flex;align-items:center;gap:8px;font-size:14px}
.mg-targets input[type=checkbox]{width:18px;height:18px;flex:none;accent-color:var(--primary-color)}
.mg-targets code{font-size:12.5px}
.mg-palette{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.mg-swatch{width:28px;height:28px;border-radius:50%;border:2px solid transparent;cursor:pointer;padding:0}
.mg-swatch[aria-pressed=true]{border-color:var(--primary-text-color);box-shadow:0 0 0 2px var(--card-background-color) inset}
.mg-palette input[type=color]{width:36px;height:30px;padding:0;border:none;background:none}
.mg-crop-preview{display:flex;flex-direction:column;gap:4px;padding:10px 12px;border-radius:10px;background:var(--secondary-background-color,rgba(0,0,0,.04));font-size:13px}
.mg-empty-state{display:flex;flex-direction:column;align-items:center;gap:10px;padding:48px 16px;text-align:center;color:var(--secondary-text-color)}
.mg-empty-state .mg-ic{--mdc-icon-size:48px;width:48px;height:48px;color:var(--disabled-text-color)}
.mg-fab{position:fixed;right:20px;bottom:20px;z-index:5;border-radius:16px;min-height:52px;padding:0 18px;box-shadow:0 4px 14px rgba(0,0,0,.25);font-size:15px}
:host(:not([narrow])) .mg-fab{display:none}
:host([narrow]) .mg-toolbar .mg-sow-top{display:none}
.mg-about{font-size:13px;color:var(--secondary-text-color)}
.mg-about a{color:var(--primary-color)}
`;

class HaMicrogreensPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._tab = localStorage.getItem(`${LS}tab`) || 'board';
    this._tlDays = Number(localStorage.getItem(`${LS}tl_days`)) || 28;
    this._tlOffset = 0;
    this._histCrop = '';
    this._settings = null;
    this.ctx = { host: this, hass: () => this._hass, i18n: null, snap: () => this._snap };
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._menu) this._menu.hass = hass;
    if (first) this._boot();
    else if (this._i18n && this._i18n.lang !== hassLang(hass)) this._boot();  // user changed language
  }

  set narrow(n) {
    this._narrow = !!n;
    this.toggleAttribute('narrow', this._narrow);
    if (this._menu) this._menu.narrow = this._narrow;
  }

  set panel(_p) {}
  set route(_r) {}

  connectedCallback() {
    upgradeProperties(this, ['hass', 'narrow', 'panel', 'route']);
    if (this._hass && this._i18n && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsub) { this._unsub(); this._unsub = null; }
  }

  get _admin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  async _boot() {
    await coreReady;
    this._i18n = await loadI18n(this._hass);
    this.ctx.i18n = this._i18n;
    this._renderShell();
    if (!this._unsub) this._subscribe();
    else this._renderContent(true);
  }

  _subscribe() {
    this._unsub = subscribe(this._hass, (snap, err) => {
      this._snap = snap;
      this._err = err;
      this._renderContent();
    });
  }

  // ------------------------------------------------------------------ shell

  _renderShell() {
    const t = this._i18n;
    const tabs = TABS.filter((x) => !x.admin || this._admin);
    if (!tabs.some((x) => x.id === this._tab)) this._tab = 'board';
    this.shadowRoot.innerHTML = `<style>${STYLES}${PANEL_STYLES}</style>
      <div class="mg-app">
        <header class="mg-toolbar">
          <ha-menu-button></ha-menu-button>
          <div class="mg-brand">${icon('mdi:sprout')}<span>Microgreens</span></div>
          <button type="button" class="mg-btn mg-sow-top" data-act="sow">${icon('mdi:seed')}<span>${t.t('btn.sow')}</span></button>
        </header>
        <nav class="mg-tabs" role="tablist" aria-label="Microgreens">${tabs.map((x) => `<button type="button" role="tab" class="mg-tab" data-tab="${x.id}" aria-selected="${x.id === this._tab}">${icon(x.icon)}<span>${t.t(`tab.${x.id}`)}</span></button>`).join('')}</nav>
        <main class="mg-main"><div class="mg-content" role="tabpanel"></div></main>
        <button type="button" class="mg-btn primary mg-fab" data-act="sow">${icon('mdi:seed')}<span>${t.t('btn.sow')}</span></button>
      </div>`;
    this._menu = this.shadowRoot.querySelector('ha-menu-button');
    this._menu.hass = this._hass;
    this._menu.narrow = this._narrow;
    this._content = this.shadowRoot.querySelector('.mg-content');
    this.shadowRoot.querySelector('.mg-tabs').addEventListener('click', (e) => {
      const b = e.target.closest('[data-tab]');
      if (b) this._setTab(b.dataset.tab);
    });
    this.shadowRoot.querySelector('.mg-app').addEventListener('click', (e) => this._onClick(e));
    this.shadowRoot.querySelector('.mg-app').addEventListener('change', (e) => this._onChange(e));
  }

  _setTab(id) {
    this._tab = id;
    if (id === 'settings') this._settings = null;  // refetch: the options flow may have changed them
    localStorage.setItem(`${LS}tab`, id);
    this.shadowRoot.querySelectorAll('.mg-tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === id)));
    this.shadowRoot.querySelector('.mg-main').scrollTop = 0;
    this._renderContent(true);
  }

  // A push re-renders the open tab, except Settings: nothing there comes from
  // the snapshot, and re-rendering it would throw away unsaved edits.
  _renderContent(force = false) {
    if (!this._content) return;
    if (!force && this._tab === 'settings' && this._content.querySelector('#mg-settings')) return;
    const t = this._i18n;
    if (this._err) {
      this._content.innerHTML = `<div class="mg-empty-state">${icon('mdi:alert-circle-outline')}<div>${t.t('panel.error')}</div><code>${esc(errorText(t, this._err))}</code></div>`;
      return;
    }
    if (!this._snap) {
      this._content.innerHTML = `<div class="mg-empty-state">${icon('mdi:sprout')}<div>${t.t('panel.loading')}</div></div>`;
      return;
    }
    if (!this._snap.loaded) {
      this._content.innerHTML = `<div class="mg-empty-state">${icon('mdi:power-plug-off-outline')}<div>${t.t('panel.not_loaded')}</div></div>`;
      return;
    }
    const render = {
      board: () => this._board(),
      timeline: () => this._timeline(),
      crops: () => this._crops(),
      plots: () => this._plots(),
      history: () => this._history(),
      settings: () => this._settingsTab(),
    }[this._tab] || (() => this._board());
    this._content.innerHTML = render();
    if (this._tab === 'settings') this._loadSettings();
  }

  // ------------------------------------------------------------------ events

  _onClick(e) {
    const el = e.target.closest('[data-act]');
    if (!el || !this.shadowRoot.contains(el)) return;
    const act = el.dataset.act;
    if (!act) return;
    const snap = this._snap;
    if (!snap || !snap.loaded) return;
    switch (act) {
      case 'tl-sow': return this._timelineSow(e, el);
      case 'tl-move': this._tlOffset += Number(el.dataset.days); return this._renderContent(true);
      case 'tl-today': this._tlOffset = 0; return this._renderContent(true);
      case 'tl-range': this._tlDays = Number(el.dataset.days); localStorage.setItem(`${LS}tl_days`, String(this._tlDays)); return this._renderContent(true);
      case 'crop-new': return this._cropDialog(null);
      case 'crop-edit': return this._cropDialog(el.dataset.id);
      case 'crop-copy': return this._cropDialog(el.dataset.id, true);
      case 'crop-sow': return sowDialog(this.ctx, { profile: el.dataset.id });
      case 'plot-new': return this._plotDialog(null);
      case 'plot-bulk': return this._bulkPlotsDialog();
      case 'plot-edit': return this._plotDialog(el.dataset.plot);
      case 'plot-delete': return this._deletePlot(el.dataset.plot, el);
      case 'plot-move': return this._movePlot(el.dataset.plot, Number(el.dataset.dir), el);
      case 'settings-save': return this._saveSettings(el);
      case 'notify-test': return this._notify(el, 'notify/test');
      case 'notify-digest': return this._notify(el, 'notify/digest');
      case 'export': return this._export(el);
      case 'import': return this.shadowRoot.querySelector('#mg-import-file').click();
      case 'target-add': return this._addTarget();
      default: return handleAction(this.ctx, el);
    }
  }

  _onChange(e) {
    const el = e.target;
    if (el.id === 'mg-hist-crop') { this._histCrop = el.value; this._renderContent(true); }
    if (el.id === 'mg-import-file' && el.files && el.files[0]) this._import(el.files[0], el);
  }

  // ------------------------------------------------------------------ board

  _board() {
    const t = this._i18n;
    const snap = this._snap;
    const count = (pred) => snap.plots.filter(pred).length;
    const growing = count((p) => ['covered', 'growing'].includes(p.status));
    const ready = count((p) => ['ready', 'overdue'].includes(p.status));
    const empty = count((p) => p.status === 'empty');
    const upcoming = snap.plantings.filter((p) => !p.planned && p.computed.days_to_harvest > 0).sort((a, b) => a.computed.days_to_harvest - b.computed.days_to_harvest)[0];
    const stat = (ic, n, label, color) => `<div class="mg-stat">${icon(ic)}<div><b style="color:${color}">${n}</b><br><span>${label}</span></div></div>`;
    const summary = `<div class="mg-summary">
      ${stat('mdi:sprout', growing, t.t('board.stat_growing', { count: growing }), 'var(--mg-growing)')}
      ${stat('mdi:basket', ready, t.t('board.stat_ready', { count: ready }), 'var(--mg-ready)')}
      ${stat('mdi:tray', empty, t.t('board.stat_empty', { count: empty }), 'var(--secondary-text-color)')}
      ${upcoming ? `<div class="mg-stat">${icon('mdi:calendar-check')}<div><b>${esc(fmtDate(upcoming.computed.harvest_start, t.lang, { day: 'numeric', month: 'short' }))}</b><br><span>${t.t('board.next_harvest', { crop: upcoming.crop.name })}</span></div></div>` : ''}
    </div>`;
    if (!snap.plots.length) {
      return `${summary}<div class="mg-card mg-empty-state">${icon('mdi:tray-plus')}<div>${t.t('board.no_plots')}</div>${this._admin ? `<button type="button" class="mg-btn primary" data-act="plot-bulk">${icon('mdi:plus')}<span>${t.t('btn.add_plots')}</span></button>` : ''}</div>`;
    }
    const today = `<div class="mg-card mg-today-card"><h3>${icon('mdi:clipboard-check-outline')}${t.t('board.today', { date: fmtDate(snap.today, t.lang, { weekday: 'long', day: 'numeric', month: 'long' }) })}</h3>${taskList(t, snap)}</div>`;
    const tiles = `<div class="mg-tiles">${snap.plots.map((p) => plotTile(t, snap, p)).join('')}</div>`;
    return `${summary}<div class="mg-board">${today}${tiles}</div>`;
  }

  // ------------------------------------------------------------------ timeline

  _tlStart() {
    // A quarter of the range in the past, so the current trays are in view.
    return addDays(this._snap.today, -Math.round(this._tlDays / 4) + this._tlOffset);
  }

  _timeline() {
    const t = this._i18n;
    const step = Math.max(7, Math.round(this._tlDays / 2));
    const start = this._tlStart();
    const end = addDays(start, this._tlDays - 1);
    const range = RANGES.map((d) => `<button type="button" data-act="tl-range" data-days="${d}" aria-pressed="${d === this._tlDays}">${t.t('timeline.weeks', { count: d / 7 })}</button>`).join('');
    return `<div class="mg-tl-tools">
        <button type="button" class="mg-btn icon-only" data-act="tl-move" data-days="${-step}" aria-label="${t.t('btn.earlier')}" title="${t.t('btn.earlier')}">${icon('mdi:chevron-left')}</button>
        <button type="button" class="mg-btn" data-act="tl-today">${t.t('rel.today')}</button>
        <button type="button" class="mg-btn icon-only" data-act="tl-move" data-days="${step}" aria-label="${t.t('btn.later')}" title="${t.t('btn.later')}">${icon('mdi:chevron-right')}</button>
        <b>${esc(fmtDate(start, t.lang, { day: 'numeric', month: 'short' }))} - ${esc(fmtDate(end, t.lang, { day: 'numeric', month: 'short', year: 'numeric' }))}</b>
        <span class="mg-seg-btns">${range}</span>
        <span class="mg-muted">${t.t('timeline.hint')}</span>
      </div>
      <div class="mg-card">${timeline(t, this._snap, { start, days: this._tlDays })}</div>`;
  }

  _timelineSow(e, track) {
    const rect = track.getBoundingClientRect();
    const idx = Math.floor(((e.clientX - rect.left) / rect.width) * this._tlDays);
    const date = addDays(this._tlStart(), Math.max(0, Math.min(this._tlDays - 1, idx)));
    sowDialog(this.ctx, { plot: track.dataset.plot, date: date < this._snap.today ? this._snap.today : date });
  }

  // ------------------------------------------------------------------ crops

  _crops() {
    const t = this._i18n;
    const snap = this._snap;
    const stats = new Map(cropStats(snap.history).map((s) => [s.key, s]));
    const active = new Map();
    for (const p of snap.plantings) active.set(p.profile_id, (active.get(p.profile_id) || 0) + 1);
    const cards = snap.profiles.map((p) => {
      const s = stats.get(p.id);
      const total = p.cover_days + p.light_days;
      const span = total + p.harvest_window_days;
      const w = (n) => ((n / span) * 100).toFixed(2);
      const bar = `<div class="mg-stagebar">${p.cover_days ? `<span class="mg-seg mg-seg-cover" style="left:0;width:${w(p.cover_days)}%"></span>` : ''}<span class="mg-seg mg-seg-light" style="left:${w(p.cover_days)}%;width:${w(p.light_days)}%"></span><span class="mg-seg mg-seg-window" style="left:${w(total)}%;width:${w(p.harvest_window_days)}%"></span></div>`;
      const st = [];
      if (active.get(p.id)) st.push(`<span>${icon('mdi:sprout')}${t.t('crops.active', { count: active.get(p.id) })}</span>`);
      if (s) {
        st.push(`<span>${icon('mdi:history')}${t.t('crops.grown', { count: s.trays })}</span>`);
        if (s.avgYield != null) st.push(`<span>${icon('mdi:scale')}${t.t('crops.avg_yield', { grams: t.num(s.avgYield) })}</span>`);
        if (s.avgRating != null) st.push(`<span>${icon('mdi:star')}${t.num(s.avgRating, 1)}</span>`);
      }
      if (p.seed_grams != null) st.push(`<span>${icon('mdi:seed-outline')}${t.t('crops.seed', { grams: t.num(p.seed_grams, 1) })}</span>`);
      return `<div class="mg-card mg-crop" style="--crop-color:${safeColor(p.color)}">
        <div class="mg-crop-top"><b>${esc(p.name)}</b><span class="mg-crop-days">${total}<small>${t.t('crops.days_short')}</small></span></div>
        <div class="mg-muted mg-small">${cropSummary(t, p)}</div>
        ${bar}
        ${st.length ? `<div class="mg-crop-stats">${st.join('')}</div>` : ''}
        ${p.notes ? `<div class="mg-notes">${esc(p.notes)}</div>` : ''}
        <div class="mg-actions">
          <button type="button" class="mg-btn primary" data-act="crop-sow" data-id="${esc(p.id)}">${icon('mdi:seed')}<span>${t.t('btn.sow')}</span></button>
          ${this._admin ? `<button type="button" class="mg-btn" data-act="crop-edit" data-id="${esc(p.id)}">${icon('mdi:pencil')}<span>${t.t('btn.edit')}</span></button>
          <button type="button" class="mg-btn icon-only" data-act="crop-copy" data-id="${esc(p.id)}" title="${t.t('btn.duplicate')}" aria-label="${t.t('btn.duplicate')}">${icon('mdi:content-copy')}</button>` : ''}
        </div></div>`;
    }).join('');
    return `<div class="mg-section-head"><h2>${t.t('tab.crops')}</h2>${this._admin ? `<button type="button" class="mg-btn primary" data-act="crop-new">${icon('mdi:plus')}<span>${t.t('btn.new_crop')}</span></button>` : ''}</div>
      ${cards ? `<div class="mg-crop-grid">${cards}</div>` : `<div class="mg-card mg-empty-state">${icon('mdi:sprout-outline')}<div>${t.t('crops.none')}</div></div>`}`;
  }

  _cropDialog(id, copy = false) {
    const t = this._i18n;
    const snap = this._snap;
    const src = id ? snap.profileById.get(id) : null;
    const base = src || { name: '', color: PALETTE[snap.profiles.length % PALETTE.length], soak_hours: 0, cover_days: 3, light_days: 7, harvest_window_days: 3, water_every_days: 1, seed_grams: null, notes: '' };
    const editing = src && !copy;
    const name = copy ? t.tt('crops.copy_name', { name: base.name }) : base.name;
    const swatches = PALETTE.map((c) => `<button type="button" class="mg-swatch" data-color="${c}" style="background:${c}" aria-pressed="${c === base.color}" aria-label="${c}"></button>`).join('');
    const body = `<form class="mg-form" novalidate>
      <label class="mg-field"><span>${t.t('field.name')}</span><input type="text" name="name" value="${esc(name)}" maxlength="60" required></label>
      <div class="mg-field"><span>${t.t('field.color')}</span><div class="mg-palette">${swatches}<input type="color" name="color" value="${esc(safeColor(base.color))}" aria-label="${t.t('field.color')}"></div></div>
      ${stageFields(t, base)}
      <label class="mg-field"><span>${t.t('field.seed_grams')}</span><input type="number" name="seed_grams" min="0" step="0.1" value="${base.seed_grams == null ? '' : esc(base.seed_grams)}"><small>${t.t('hint.seed_grams')}</small></label>
      <label class="mg-field"><span>${t.t('field.notes')}</span><textarea name="notes" rows="3" maxlength="1000">${esc(base.notes)}</textarea></label>
      <div class="mg-crop-preview"></div>
      <div class="mg-actions spread">
        ${editing ? `<button type="button" class="mg-btn danger" data-delete>${icon('mdi:delete-outline')}<span>${t.t('btn.delete')}</span></button>` : '<span></span>'}
        <span class="mg-actions" style="margin:0"><button type="button" class="mg-btn" data-close>${t.t('btn.cancel')}</button><button type="submit" class="mg-btn primary">${t.t('btn.save')}</button></span>
      </div></form>`;
    openDialog(this, t, {
      title: editing ? t.t('dialog.edit_crop') : t.t('dialog.new_crop'),
      body,
      wide: true,
      onReady: (dlg) => {
        const form = dlg.querySelector('form');
        const preview = () => {
          const v = readForm(form, ['cover_days', 'light_days', 'harvest_window_days', 'water_every_days', 'soak_hours', 'color']);
          const c = { cover_days: +v.cover_days || 0, light_days: Math.max(1, +v.light_days || 1), harvest_window_days: Math.max(1, +v.harvest_window_days || 1), water_every_days: +v.water_every_days || 0, soak_hours: +v.soak_hours || 0 };
          const total = c.cover_days + c.light_days;
          const span = total + c.harvest_window_days;
          const w = (n) => ((n / span) * 100).toFixed(2);
          form.querySelector('.mg-crop-preview').innerHTML = `<div>${cropDot(v.color)}<b>${t.t('crops.preview_total', { count: total })}</b></div>
            <div class="mg-stagebar large">${c.cover_days ? `<span class="mg-seg mg-seg-cover" style="left:0;width:${w(c.cover_days)}%"></span>` : ''}<span class="mg-seg mg-seg-light" style="left:${w(c.cover_days)}%;width:${w(c.light_days)}%"></span><span class="mg-seg mg-seg-window" style="left:${w(total)}%;width:${w(c.harvest_window_days)}%"></span></div>
            <div class="mg-muted">${cropSummary(t, c)}</div>`;
        };
        form.addEventListener('input', preview);
        form.addEventListener('click', (e) => {
          const sw = e.target.closest('[data-color]');
          if (sw) {
            form.color.value = sw.dataset.color;
            form.querySelectorAll('.mg-swatch').forEach((b) => b.setAttribute('aria-pressed', String(b === sw)));
            preview();
          }
          const del = e.target.closest('[data-delete]');
          if (del && confirm(t.tt('confirm.delete_crop', { crop: src.name }))) {
            busy(del, async () => { await ws(this._hass, 'profile/delete', { profile_id: src.id }); dlg.close(); toast(this, t.tt('msg.deleted')); }, (err) => dlg.showError(err));
          }
        });
        preview();
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const v = readForm(form, ['name', 'color', 'cover_days', 'light_days', 'harvest_window_days', 'water_every_days', 'soak_hours', 'seed_grams', 'notes']);
          const profile = { name: v.name.trim(), color: v.color, notes: v.notes.trim(), seed_grams: v.seed_grams === '' ? null : Number(v.seed_grams) };
          for (const k of ['cover_days', 'light_days', 'harvest_window_days', 'water_every_days', 'soak_hours']) profile[k] = Number(v[k]);
          if (editing) profile.id = src.id;
          busy(form.querySelector('[type="submit"]'), async () => {
            await ws(this._hass, 'profile/save', { profile });
            dlg.close();
            toast(this, t.tt('msg.saved'));
          }, (err) => dlg.showError(err));
        });
      },
    });
  }

  // ------------------------------------------------------------------ plots

  _plots() {
    const t = this._i18n;
    const snap = this._snap;
    const admin = this._admin;
    const rows = snap.plots.map((p, i) => {
      const cur = p.current ? snap.plantingById.get(p.current) : null;
      return `<tr>
        <td><b>${esc(p.name)}</b>${p.location ? `<div class="mg-muted mg-small">${esc(p.location)}</div>` : ''}</td>
        <td><code class="mg-small">${esc(p.id)}</code></td>
        <td>${statusPill(t, p.status)}</td>
        <td>${cur ? `<span data-act="open" data-id="${esc(cur.id)}" style="cursor:pointer">${cropDot(cur.crop.color)}${esc(cur.crop.name)}</span>` : '<span class="mg-muted">-</span>'}</td>
        <td><div class="mg-row-actions">
          ${admin ? `<button type="button" class="mg-btn icon-only" data-act="plot-move" data-plot="${esc(p.id)}" data-dir="-1" ${i === 0 ? 'disabled' : ''} aria-label="${t.t('btn.move_up')}" title="${t.t('btn.move_up')}">${icon('mdi:arrow-up')}</button>
          <button type="button" class="mg-btn icon-only" data-act="plot-move" data-plot="${esc(p.id)}" data-dir="1" ${i === snap.plots.length - 1 ? 'disabled' : ''} aria-label="${t.t('btn.move_down')}" title="${t.t('btn.move_down')}">${icon('mdi:arrow-down')}</button>
          <button type="button" class="mg-btn icon-only" data-act="plot-edit" data-plot="${esc(p.id)}" aria-label="${t.t('btn.edit')}" title="${t.t('btn.edit')}">${icon('mdi:pencil')}</button>
          <button type="button" class="mg-btn icon-only danger" data-act="plot-delete" data-plot="${esc(p.id)}" aria-label="${t.t('btn.delete')}" title="${t.t('btn.delete')}">${icon('mdi:delete-outline')}</button>` : ''}
          ${p.status === 'empty' ? `<button type="button" class="mg-btn" data-act="sow" data-plot="${esc(p.id)}">${icon('mdi:seed')}<span>${t.t('btn.sow')}</span></button>` : ''}
        </div></td></tr>`;
    }).join('');
    return `<div class="mg-section-head"><h2>${t.t('tab.plots')}</h2>${admin ? `<span class="mg-actions" style="margin:0"><button type="button" class="mg-btn" data-act="plot-bulk">${icon('mdi:plus-box-multiple-outline')}<span>${t.t('btn.add_plots')}</span></button><button type="button" class="mg-btn primary" data-act="plot-new">${icon('mdi:plus')}<span>${t.t('btn.add_plot')}</span></button></span>` : ''}</div>
      <div class="mg-card mg-table-wrap">${rows ? `<table class="mg-table"><thead><tr><th>${t.t('field.name')}</th><th>${t.t('field.id')}</th><th>${t.t('field.status')}</th><th>${t.t('field.crop')}</th><th></th></tr></thead><tbody>${rows}</tbody></table>` : `<div class="mg-empty-state">${icon('mdi:tray-plus')}<div>${t.t('board.no_plots')}</div></div>`}</div>
      <p class="mg-muted mg-small">${t.t('plots.hint')}</p>`;
  }

  _plotDialog(plotId) {
    const t = this._i18n;
    const plot = plotId ? this._snap.plotById.get(plotId) : null;
    const body = `<form class="mg-form" novalidate>
      <label class="mg-field"><span>${t.t('field.name')}</span><input type="text" name="name" value="${esc(plot ? plot.name : '')}" maxlength="60" required></label>
      <label class="mg-field"><span>${t.t('field.location')}</span><input type="text" name="location" value="${esc(plot ? plot.location : '')}" maxlength="60" placeholder="${t.t('hint.location')}"></label>
      ${plot ? '' : `<label class="mg-field"><span>${t.t('field.id')}</span><input type="text" name="id" maxlength="32" pattern="[A-Za-z0-9_-]+" placeholder="A7"><small>${t.t('hint.plot_id')}</small></label>`}
      <div class="mg-actions end"><button type="button" class="mg-btn" data-close>${t.t('btn.cancel')}</button><button type="submit" class="mg-btn primary">${t.t('btn.save')}</button></div></form>`;
    openDialog(this, t, {
      title: plot ? t.t('dialog.edit_plot') : t.t('dialog.new_plot'),
      body,
      onReady: (dlg) => {
        const form = dlg.querySelector('form');
        form.name.focus();
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          const payload = { name: form.name.value.trim(), location: form.location.value.trim() };
          if (plot) payload.id = plot.id;
          else if (form.id.value.trim()) payload.id = form.id.value.trim();
          busy(form.querySelector('[type="submit"]'), async () => { await ws(this._hass, 'plot/save', { plot: payload }); dlg.close(); toast(this, t.tt('msg.saved')); }, (err) => dlg.showError(err));
        });
      },
    });
  }

  _bulkPlotsDialog() {
    const t = this._i18n;
    const body = `<form class="mg-form" novalidate>
      <p class="mg-muted mg-small" style="margin:0">${t.t('plots.bulk_hint')}</p>
      <div class="mg-grid-fields">
        <label class="mg-field"><span>${t.t('field.prefix')}</span><input type="text" name="prefix" value="B" maxlength="20" pattern="[A-Za-z0-9_-]*"></label>
        <label class="mg-field"><span>${t.t('field.first_number')}</span><input type="number" name="first" value="1" min="0" max="999"></label>
        <label class="mg-field"><span>${t.t('field.count')}</span><input type="number" name="count" value="6" min="1" max="50"></label>
      </div>
      <label class="mg-field"><span>${t.t('field.location')}</span><input type="text" name="location" maxlength="60" placeholder="${t.t('hint.location')}"></label>
      <div class="mg-preview mg-bulk-preview"></div>
      <div class="mg-actions end"><button type="button" class="mg-btn" data-close>${t.t('btn.cancel')}</button><button type="submit" class="mg-btn primary">${t.t('btn.add')}</button></div></form>`;
    openDialog(this, t, {
      title: t.t('dialog.add_plots'),
      body,
      onReady: (dlg) => {
        const form = dlg.querySelector('form');
        const ids = () => {
          const n = Math.max(1, Math.min(50, Number(form.count.value) || 1));
          const first = Math.max(0, Number(form.first.value) || 0);
          return Array.from({ length: n }, (_, i) => `${form.prefix.value.trim()}${first + i}`);
        };
        const update = () => { form.querySelector('.mg-bulk-preview').textContent = ids().join(', '); };
        form.addEventListener('input', update);
        update();
        form.addEventListener('submit', (e) => {
          e.preventDefault();
          busy(form.querySelector('[type="submit"]'), async () => {
            let added = 0;
            for (const id of ids()) {
              if (this._snap.plotById.has(id)) continue;
              await ws(this._hass, 'plot/save', { plot: { id, name: t.tt('plots.default_name', { id }), location: form.location.value.trim() } });
              added += 1;
            }
            dlg.close();
            toast(this, t.tt('msg.plots_added', { count: added }));
          }, (err) => dlg.showError(err));
        });
      },
    });
  }

  _deletePlot(plotId, el) {
    const t = this._i18n;
    const plot = this._snap.plotById.get(plotId);
    const inUse = this._snap.plantings.some((p) => p.plot_id === plotId);
    if (!confirm(t.tt(inUse ? 'confirm.delete_plot_in_use' : 'confirm.delete_plot', { plot: plot.name }))) return;
    busy(el, () => ws(this._hass, 'plot/delete', { plot_id: plotId, force: inUse }).then(() => toast(this, t.tt('msg.deleted'))), (err) => toast(this, errorText(t, err), { error: true }));
  }

  _movePlot(plotId, dir, el) {
    const ids = this._snap.plots.map((p) => p.id);
    const i = ids.indexOf(plotId);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    busy(el, () => ws(this._hass, 'plot/reorder', { plot_ids: ids }), (err) => toast(this, errorText(this._i18n, err), { error: true }));
  }

  // ------------------------------------------------------------------ history

  _history() {
    const t = this._i18n;
    const snap = this._snap;
    const stats = cropStats(snap.history);
    if (!snap.history.length) {
      return `<div class="mg-section-head"><h2>${t.t('tab.history')}</h2></div><div class="mg-card mg-empty-state">${icon('mdi:basket-outline')}<div>${t.t('history.none')}</div></div>`;
    }
    const total = stats.reduce((a, s) => a + s.totalYield, 0);
    const statRows = stats.map((s) => `<tr>
      <td>${cropDot(s.color)}${esc(s.name)}</td><td class="num">${s.trays}</td>
      <td class="num">${s.successRate == null ? '-' : `${t.num(s.successRate * 100)}%`}</td>
      <td class="num">${s.avgDays == null ? '-' : t.num(s.avgDays, 1)}</td>
      <td class="num">${s.avgYield == null ? '-' : `${t.num(s.avgYield)} g`}</td>
      <td class="num">${s.totalYield ? `${t.num(s.totalYield)} g` : '-'}</td>
      <td class="num">${s.avgRating == null ? '-' : `${t.num(s.avgRating, 1)} ★`}</td></tr>`).join('');
    const crops = [...new Map(snap.history.map((h) => [h.profile_id || h.crop.name, h.crop.name])).entries()];
    const filtered = snap.history.filter((h) => !this._histCrop || (h.profile_id || h.crop.name) === this._histCrop);
    const rows = filtered.map((h) => `<tr data-act="history" data-id="${esc(h.id)}">
      <td>${esc(fmtDate(h.ended_on, t.lang, { day: 'numeric', month: 'short', year: 'numeric' }))}</td>
      <td>${cropDot(h.crop.color)}${esc(h.crop.name)}</td><td>${esc(h.plot_name)}</td>
      <td class="num">${daysBetween(h.sown_on, h.ended_on)}</td>
      <td class="num">${h.yield_grams == null ? '-' : `${t.num(h.yield_grams, 1)} g`}</td>
      <td class="num">${h.rating ? '★'.repeat(h.rating) : '-'}</td>
      <td>${h.outcome === 'harvested' ? t.t('outcome.harvested') : `<span style="color:var(--mg-overdue)">${t.t(`reason.${h.reason || 'other'}`)}</span>`}</td></tr>`).join('');
    return `<div class="mg-section-head"><h2>${t.t('tab.history')}</h2><span class="mg-muted">${t.t('history.total', { grams: t.num(total), count: snap.history.length })}</span></div>
      <div class="mg-stack">
        <div class="mg-card mg-table-wrap"><h3>${icon('mdi:chart-box-outline')}${t.t('history.by_crop')}</h3><table class="mg-table"><thead><tr><th>${t.t('field.crop')}</th><th class="num">${t.t('history.trays')}</th><th class="num">${t.t('history.success')}</th><th class="num">${t.t('history.avg_days')}</th><th class="num">${t.t('history.avg_yield')}</th><th class="num">${t.t('history.total_yield')}</th><th class="num">${t.t('field.rating')}</th></tr></thead><tbody>${statRows}</tbody></table></div>
        <div class="mg-card mg-table-wrap">
          <div class="mg-filters"><h3 style="margin:0;flex:1">${icon('mdi:format-list-bulleted')}${t.t('history.entries')}</h3>
            <select id="mg-hist-crop" aria-label="${t.t('field.crop')}"><option value="">${t.t('history.all_crops')}</option>${crops.map(([k, n]) => `<option value="${esc(k)}"${k === this._histCrop ? ' selected' : ''}>${esc(n)}</option>`).join('')}</select></div>
          <table class="mg-table"><thead><tr><th>${t.t('field.ended_on')}</th><th>${t.t('field.crop')}</th><th>${t.t('field.plot')}</th><th class="num">${t.t('history.days')}</th><th class="num">${t.t('field.yield_grams')}</th><th class="num">${t.t('field.rating')}</th><th>${t.t('history.outcome')}</th></tr></thead><tbody>${rows}</tbody></table>
        </div>
      </div>`;
  }

  // ------------------------------------------------------------------ settings

  _settingsTab() {
    const t = this._i18n;
    return `<div class="mg-section-head"><h2>${t.t('tab.settings')}</h2></div>
      <div class="mg-stack" id="mg-settings">
        <div class="mg-card"><h3>${icon('mdi:bell-outline')}${t.t('settings.notifications')}</h3><div class="mg-settings-body">${this._settings ? this._settingsForm() : `<span class="mg-muted">${t.t('panel.loading')}</span>`}</div></div>
        <div class="mg-card"><h3>${icon('mdi:database-export-outline')}${t.t('settings.backup')}</h3>
          <p class="mg-muted mg-small" style="margin-top:0">${t.t('settings.backup_hint')}</p>
          <div class="mg-actions"><button type="button" class="mg-btn" data-act="export">${icon('mdi:download')}<span>${t.t('btn.export')}</span></button><button type="button" class="mg-btn" data-act="import">${icon('mdi:upload')}<span>${t.t('btn.import')}</span></button><input type="file" id="mg-import-file" accept="application/json,.json" hidden></div></div>
        <div class="mg-card mg-about"><h3>${icon('mdi:information-outline')}${t.t('settings.about')}</h3>${t.t('settings.version', { version: this._snap.version || '?' })} · <a href="https://github.com/3dg1luk43/ha-microgreens" target="_blank" rel="noopener noreferrer">GitHub</a></div>
      </div>`;
  }

  _settingsForm() {
    const t = this._i18n;
    const o = this._settings.options;
    const targets = [...new Set([...this._settings.targets, ...o.notify_targets])];
    const sw = (key, label, hint, extra = '') => `<label class="mg-switch"><div><span>${label}</span><small>${hint}</small></div><span class="mg-actions" style="margin:0;align-items:center">${extra}<input type="checkbox" name="${key}"${o[key] ? ' checked' : ''}></span></label>`;
    const time = (key) => `<input type="time" name="${key}" value="${esc(String(o[key]).slice(0, 5))}" aria-label="${t.t(`settings.${key}`)}">`;
    return `<form class="mg-settings-form" novalidate>
      <div class="mg-field"><span>${t.t('settings.targets')}</span><small>${t.t('settings.targets_hint')}</small>
        <div class="mg-targets">${targets.length ? targets.map((x) => `<label><input type="checkbox" name="target" value="${esc(x)}"${o.notify_targets.includes(x) ? ' checked' : ''}><code>${esc(x)}</code></label>`).join('') : `<span class="mg-muted mg-small">${t.t('settings.no_targets')}</span>`}</div>
        <span class="mg-actions" style="margin:0"><input type="text" id="mg-target-new" placeholder="notify.mobile_app_phone" style="flex:1;font:inherit;padding:8px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--secondary-background-color);color:var(--primary-text-color)"><button type="button" class="mg-btn" data-act="target-add">${t.t('btn.add')}</button></span>
      </div>
      ${sw('digest_enabled', t.t('settings.digest_enabled'), t.t('settings.digest_hint'), time('digest_time'))}
      ${sw('reminder_enabled', t.t('settings.reminder_enabled'), t.t('settings.reminder_hint'), time('reminder_time'))}
      ${sw('persistent_notification', t.t('settings.persistent_notification'), t.t('settings.persistent_hint'))}
      ${sw('notification_actions', t.t('settings.notification_actions'), t.t('settings.actions_hint'))}
      <div class="mg-actions spread"><span class="mg-actions" style="margin:0">
        <button type="button" class="mg-btn" data-act="notify-test">${icon('mdi:bell-ring-outline')}<span>${t.t('btn.test')}</span></button>
        <button type="button" class="mg-btn" data-act="notify-digest">${icon('mdi:message-text-outline')}<span>${t.t('btn.digest_now')}</span></button></span>
        <button type="button" class="mg-btn primary" data-act="settings-save">${t.t('btn.save')}</button></div>
    </form>`;
  }

  async _loadSettings() {
    if (this._settingsLoading || this._settings) return;
    this._settingsLoading = true;
    try {
      this._settings = await ws(this._hass, 'settings/get');
      if (this._tab === 'settings') {
        const body = this.shadowRoot.querySelector('.mg-settings-body');
        if (body) body.innerHTML = this._settingsForm();
      }
    } catch (err) {
      toast(this, errorText(this._i18n, err), { error: true });
    } finally {
      this._settingsLoading = false;
    }
  }

  _addTarget() {
    const input = this.shadowRoot.querySelector('#mg-target-new');
    const value = input.value.trim();
    if (!value.startsWith('notify.')) { toast(this, this._i18n.tt('settings.target_invalid'), { error: true }); return; }
    this._settings.options = this._readSettings();
    if (!this._settings.targets.includes(value)) this._settings.targets.push(value);
    if (!this._settings.options.notify_targets.includes(value)) this._settings.options.notify_targets.push(value);
    this.shadowRoot.querySelector('.mg-settings-body').innerHTML = this._settingsForm();
  }

  _readSettings() {
    const form = this.shadowRoot.querySelector('.mg-settings-form');
    const v = readForm(form, ['digest_enabled', 'digest_time', 'reminder_enabled', 'reminder_time', 'persistent_notification', 'notification_actions']);
    v.notify_targets = [...form.querySelectorAll('[name="target"]:checked')].map((x) => x.value);
    return v;
  }

  _saveSettings(el) {
    const t = this._i18n;
    const options = this._readSettings();
    busy(el, async () => {
      const res = await ws(this._hass, 'settings/save', { options });
      this._settings.options = res.options;
      toast(this, t.tt('msg.saved'));
    }, (err) => toast(this, errorText(t, err), { error: true }));
  }

  _notify(el, type) {
    const t = this._i18n;
    busy(el, async () => {
      const res = await ws(this._hass, type);
      if (type === 'notify/test') toast(this, t.tt('msg.test_sent', { count: res.sent }));
      else toast(this, t.tt(res.sent ? 'msg.digest_sent' : 'msg.digest_empty'));
    }, (err) => toast(this, errorText(t, err), { error: true }));
  }

  _export(el) {
    busy(el, async () => {
      const data = await ws(this._hass, 'backup/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `microgreens-backup-${this._snap.today}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    }, (err) => toast(this, errorText(this._i18n, err), { error: true }));
  }

  async _import(file, input) {
    const t = this._i18n;
    try {
      const backup = JSON.parse(await file.text());
      if (!confirm(t.tt('confirm.import'))) return;
      await ws(this._hass, 'backup/import', { backup });
      toast(this, t.tt('msg.imported'));
    } catch (err) {
      toast(this, err instanceof SyntaxError ? t.tt('error.invalid_backup') : errorText(t, err), { error: true });
    } finally {
      input.value = '';
    }
  }
}

if (!customElements.get('ha-microgreens-panel')) customElements.define('ha-microgreens-panel', HaMicrogreensPanel);
