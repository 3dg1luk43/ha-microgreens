// Microgreens - Home Assistant integration for planning and tracking microgreen trays.
// Copyright (C) 2026 Lukas Bandura
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// ha-microgreens-core.js - shared by the panel and the card.
//
// Loaded by both with `import('./ha-microgreens-core.js?v=<build>')`, so the two
// share one module instance (one WebSocket subscription, one i18n cache).
// Nothing here touches the DOM at import time: tests/js runs it under node.
//
// Rules (CLAUDE.md):
// * Every user-visible string goes through I18n.t() / tt(); English lives in
//   i18n/en.json. t() returns HTML-escaped text (template AND vars), so it is
//   safe in innerHTML and attributes; tt() is plain text for textContent,
//   confirm() and the like.
// * Status, dates and tasks come from the backend snapshot (schedule.py). The
//   only date maths here is layout (bar positions) and the sow dialog's preview.

const VERSION = (() => {
  try { return new URL(import.meta.url).searchParams.get('v') || ''; } catch (_) { return ''; }
})();

export const DOMAIN = 'ha_microgreens';
export const STATIC_BASE = '/ha_microgreens';
export const PANEL_PATH = '/ha-microgreens';
export const STATUSES = ['empty', 'planned', 'covered', 'growing', 'ready', 'overdue'];
export const REASONS = ['mold', 'poor_germination', 'pests', 'dried_out', 'other'];
export const TASK_ICONS = {
  harvest: 'mdi:content-cut',
  uncover: 'mdi:weather-sunny',
  water: 'mdi:watering-can',
  sow: 'mdi:seed',
  soak: 'mdi:cup-water',
};
export const STATUS_ICONS = {
  empty: 'mdi:tray',
  planned: 'mdi:calendar-clock',
  covered: 'mdi:weather-night',
  growing: 'mdi:sprout',
  ready: 'mdi:basket',
  overdue: 'mdi:basket-unfill',
};
export const PALETTE = ['#43a047', '#e53935', '#8e24aa', '#fb8c00', '#1e88e5', '#c0ca33', '#6d4c41', '#00897b', '#d81b60', '#5e35b1'];

// --------------------------------------------------------------------------
// Escaping and i18n
// --------------------------------------------------------------------------

export function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

// Only #rrggbb reaches a style attribute; anything else falls back.
export function safeColor(c, fallback = '#43a047') {
  return /^#[0-9a-fA-F]{6}$/.test(String(c || '')) ? c : fallback;
}

const _i18nCache = (globalThis.__haMicrogreensI18n = globalThis.__haMicrogreensI18n || { dicts: {}, pending: {} });

async function _fetchLang(lang) {
  if (lang in _i18nCache.dicts) return _i18nCache.dicts[lang];
  if (!_i18nCache.pending[lang]) {
    const q = VERSION ? `?v=${encodeURIComponent(VERSION)}` : '';
    _i18nCache.pending[lang] = fetch(`${STATIC_BASE}/i18n/${encodeURIComponent(lang)}.json${q}`)
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((d) => { _i18nCache.dicts[lang] = d && typeof d === 'object' ? d : null; return _i18nCache.dicts[lang]; });
  }
  return _i18nCache.pending[lang];
}

export function hassLang(hass) {
  return (hass && ((hass.locale && hass.locale.language) || hass.language)) || 'en';
}

// The user's language (exact tag, then its base: pt-BR -> pt) over English.
export async function loadI18n(hass) {
  const lang = hassLang(hass);
  const en = (await _fetchLang('en')) || {};
  let own = null;
  if (lang !== 'en') {
    own = await _fetchLang(lang);
    if (!own && lang.includes('-')) own = await _fetchLang(lang.split('-')[0]);
  }
  return new I18n(lang, own || {}, en);
}

const _plural = new Map();
function pluralCat(lang, n) {
  let pr = _plural.get(lang);
  if (pr === undefined) {
    try { pr = new Intl.PluralRules(lang); } catch (_) { pr = null; }
    _plural.set(lang, pr);
  }
  return pr ? pr.select(n) : (n === 1 ? 'one' : 'other');
}

function fill(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (m, k) => (vars && vars[k] != null ? String(vars[k]) : m));
}

export class I18n {
  constructor(lang, dict, en) {
    this.lang = lang || 'en';
    this.dict = dict || {};
    this.en = en || {};
  }

  _pick(d, key, vars) {
    if (vars && typeof vars.count === 'number') {
      const cat = pluralCat(this.lang, vars.count);
      if (d[`${key}_${cat}`] != null) return d[`${key}_${cat}`];
      if (d[`${key}_other`] != null) return d[`${key}_other`];
    }
    return d[key];
  }

  has(key) {
    return this._pick(this.dict, key, null) != null || this._pick(this.en, key, null) != null
      || this.en[`${key}_other`] != null;
  }

  // Plain text. A `count` var picks key_one / key_few / key_other.
  tt(key, vars) {
    let s = this._pick(this.dict, key, vars);
    if (s == null) s = this._pick(this.en, key, vars);
    if (s == null) s = key;
    return fill(s, vars);
  }

  // HTML-safe text.
  t(key, vars) {
    return esc(this.tt(key, vars));
  }

  num(n, digits = 0) {
    try { return new Intl.NumberFormat(this.lang, { maximumFractionDigits: digits }).format(n); } catch (_) { return String(n); }
  }
}

// --------------------------------------------------------------------------
// Dates. ISO "YYYY-MM-DD" strings in local time; never through UTC.
// --------------------------------------------------------------------------

export function parseISO(s) {
  const [y, m, d] = String(s).slice(0, 10).split('-').map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

export function toISO(dt) {
  const p = (n) => String(n).padStart(2, '0');
  return `${dt.getFullYear()}-${p(dt.getMonth() + 1)}-${p(dt.getDate())}`;
}

export function addDays(iso, n) {
  const d = parseISO(iso);
  d.setDate(d.getDate() + n);
  return toISO(d);
}

// Calendar days from a to b. Rounded, so a DST change cannot make it 0.96.
export function daysBetween(a, b) {
  return Math.round((parseISO(b) - parseISO(a)) / 86400000);
}

export function fmtDate(iso, lang, opts) {
  if (!iso) return '';
  try {
    return new Intl.DateTimeFormat(lang, opts || { weekday: 'short', day: 'numeric', month: 'short' }).format(parseISO(iso));
  } catch (_) {
    return iso;
  }
}

// "today", "tomorrow", "in 3 days", "2 days ago"
export function relDays(i18n, n) {
  if (n === 0) return i18n.tt('rel.today');
  if (n === 1) return i18n.tt('rel.tomorrow');
  if (n === -1) return i18n.tt('rel.yesterday');
  return n > 0 ? i18n.tt('rel.in_days', { count: n }) : i18n.tt('rel.days_ago', { count: -n });
}

// --------------------------------------------------------------------------
// Backend access
// --------------------------------------------------------------------------

export function ws(hass, type, payload) {
  return hass.callWS({ type: `${DOMAIN}/${type}`, ...(payload || {}) });
}

// A refused write carries code = a strings.json exceptions key; error.<code>
// in en.json is the same message for the panel.
export function errorText(i18n, err) {
  if (err && err.code) {
    const key = `error.${err.code}`;
    const vars = { ...(err.translation_placeholders || {}) };
    // The backend names a field by its key (light_days); show its label.
    if (vars.field && i18n.has(`field.${vars.field}`)) vars.field = i18n.tt(`field.${vars.field}`);
    for (const [k, v] of Object.entries(vars)) {
      if (/^\d{4}-\d{2}-\d{2}$/.test(String(v))) vars[k] = fmtDate(v, i18n.lang, { day: 'numeric', month: 'short' });
    }
    if (i18n.has(key)) return i18n.tt(key, vars);
  }
  return (err && err.message) || String(err);
}

// One subscription per connection, shared by every panel and card on the
// page. home-assistant-js-websocket resubscribes by itself after a reconnect.
const _subs = new WeakMap();

export function subscribe(hass, cb) {
  const conn = hass.connection;
  let sub = _subs.get(conn);
  if (!sub) {
    sub = { cbs: new Set(), last: null, error: null, unsub: null };
    _subs.set(conn, sub);
    const s = sub;
    s.unsub = conn.subscribeMessage((ev) => {
      s.last = indexSnapshot(ev);
      for (const f of [...s.cbs]) {
        try { f(s.last, null); } catch (e) { console.error('ha_microgreens listener', e); }
      }
    }, { type: `${DOMAIN}/subscribe` });
    s.unsub.catch((err) => {
      s.error = err;
      if (_subs.get(conn) === s) _subs.delete(conn);
      for (const f of [...s.cbs]) f(null, err);
    });
  }
  sub.cbs.add(cb);
  if (sub.last) queueMicrotask(() => sub.cbs.has(cb) && cb(sub.last, null));
  else if (sub.error) queueMicrotask(() => cb(null, sub.error));
  const s = sub;
  return () => {
    s.cbs.delete(cb);
    // Linger a little, so a dashboard re-render does not resubscribe.
    if (!s.cbs.size) {
      setTimeout(() => {
        if (s.cbs.size || _subs.get(conn) !== s) return;
        _subs.delete(conn);
        Promise.resolve(s.unsub).then((u) => u && u()).catch(() => {});
      }, 10000);
    }
  };
}

// Lookups the renderers need, built once per pushed snapshot.
export function indexSnapshot(raw) {
  if (!raw || raw.loaded === false) return { loaded: false };
  const snap = { ...raw, loaded: true };
  snap.plotById = new Map(raw.plots.map((p) => [p.id, p]));
  snap.plantingById = new Map(raw.plantings.map((p) => [p.id, p]));
  snap.profileById = new Map(raw.profiles.map((p) => [p.id, p]));
  snap.tasksByPlanting = new Map();
  for (const t of raw.tasks) {
    if (!snap.tasksByPlanting.has(t.planting_id)) snap.tasksByPlanting.set(t.planting_id, []);
    snap.tasksByPlanting.get(t.planting_id).push(t);
  }
  return snap;
}

// --------------------------------------------------------------------------
// Layout maths (pure; tests/js/core.test.mjs)
// --------------------------------------------------------------------------

// A planting's stages as [from, to) ISO ranges.
export function stageSegments(p, today) {
  const c = p.computed;
  const end = addDays(c.harvest_end, 1);
  const segs = [];
  if (p.planned && c.soak_on) segs.push({ kind: 'soak', from: c.soak_on, to: p.sown_on });
  if (c.uncover_on > p.sown_on) segs.push({ kind: 'cover', from: p.sown_on, to: c.uncover_on });
  segs.push({ kind: 'light', from: c.uncover_on, to: c.harvest_start });
  segs.push({ kind: 'window', from: c.harvest_start, to: end });
  if (!p.planned && today >= end) segs.push({ kind: 'late', from: end, to: addDays(today, 1) });
  return segs.filter((s) => s.to > s.from);
}

// Timeline rows: one per plot, bars in day units from `start` for `days` days.
export function timelineRows(snap, start, days) {
  const end = addDays(start, days);
  const rows = snap.plots.map((plot) => ({ plot, bars: [] }));
  const byPlot = new Map(rows.map((r) => [r.plot.id, r]));
  const place = (row, bar, segs) => {
    const clipped = segs
      .map((s) => ({ kind: s.kind, from: s.from < start ? start : s.from, to: s.to > end ? end : s.to }))
      .filter((s) => s.to > s.from);
    if (!clipped.length) return;
    const from = clipped[0].from;
    const to = clipped[clipped.length - 1].to;
    row.bars.push({
      ...bar,
      left: daysBetween(start, from),
      width: daysBetween(from, to),
      clipStart: segs[0].from < start,
      clipEnd: segs[segs.length - 1].to > end,
      segs: clipped.map((s) => ({ kind: s.kind, left: daysBetween(from, s.from), width: daysBetween(s.from, s.to) })),
    });
  };
  for (const p of snap.plantings) {
    const row = byPlot.get(p.plot_id);
    if (row) place(row, { type: 'planting', id: p.id, status: p.computed.status, name: p.crop.name, color: p.crop.color }, stageSegments(p, snap.today));
  }
  for (const h of snap.history || []) {
    const row = byPlot.get(h.plot_id);
    if (!row) continue;
    const kind = h.outcome === 'harvested' ? 'past' : 'failed';
    place(row, { type: 'history', id: h.id, status: h.outcome, name: h.crop.name, color: h.crop.color }, [{ kind, from: h.sown_on, to: addDays(h.ended_on, 1) }]);
  }
  for (const r of rows) r.bars.sort((a, b) => a.left - b.left);
  return rows;
}

// The sow dialog's preview of a crop sown on `iso` (display only; the backend
// computes the real dates when the planting is created).
export function previewDates(profile, iso) {
  const uncover = addDays(iso, profile.cover_days);
  const start = addDays(uncover, profile.light_days);
  return { uncover, start, end: addDays(start, Math.max(1, profile.harvest_window_days) - 1) };
}

// Per-crop history statistics.
export function cropStats(history) {
  const out = new Map();
  for (const h of history || []) {
    const key = h.profile_id || h.crop.name;
    if (!out.has(key)) out.set(key, { key, name: h.crop.name, color: h.crop.color, trays: 0, harvested: 0, discarded: 0, yields: [], days: [], ratings: [], last: null });
    const s = out.get(key);
    s.trays += 1;
    if (h.outcome === 'harvested') {
      s.harvested += 1;
      if (h.yield_grams != null) s.yields.push(h.yield_grams);
      s.days.push(daysBetween(h.sown_on, h.ended_on));
      if (h.rating) s.ratings.push(h.rating);
    } else {
      s.discarded += 1;
    }
    if (!s.last || h.ended_on > s.last) s.last = h.ended_on;
  }
  const avg = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  return [...out.values()].map((s) => ({
    ...s,
    avgYield: avg(s.yields),
    totalYield: s.yields.reduce((x, y) => x + y, 0),
    avgDays: avg(s.days),
    avgRating: avg(s.ratings),
    successRate: s.trays ? s.harvested / s.trays : null,
  })).sort((a, b) => b.trays - a.trays || a.name.localeCompare(b.name));
}

// --------------------------------------------------------------------------
// Rendering (HTML strings; every dynamic value through esc() or t())
// --------------------------------------------------------------------------

const SEG_TITLE = { soak: 'stage.soak', cover: 'stage.cover', light: 'stage.light', window: 'stage.window', late: 'stage.late', past: 'stage.past', failed: 'stage.failed' };

export function icon(name, cls = '') {
  return `<ha-icon class="mg-ic ${cls}" icon="${esc(name)}"></ha-icon>`;
}

export function statusPill(i18n, status) {
  return `<span class="mg-pill mg-st-${esc(status)}">${i18n.t(`status.${status}`)}</span>`;
}

export function cropDot(color) {
  return `<span class="mg-dot" style="background:${safeColor(color)}"></span>`;
}

export function stageBar(i18n, p, today, opts = {}) {
  const segs = stageSegments(p, today);
  if (!segs.length) return '';
  const from = segs[0].from;
  const span = Math.max(1, daysBetween(from, segs[segs.length - 1].to));
  const parts = segs.map((s) => {
    const left = (daysBetween(from, s.from) / span) * 100;
    const width = (daysBetween(s.from, s.to) / span) * 100;
    const title = i18n.t(SEG_TITLE[s.kind], { from: fmtDate(s.from, i18n.lang), to: fmtDate(addDays(s.to, -1), i18n.lang), count: daysBetween(s.from, s.to) });
    return `<span class="mg-seg mg-seg-${s.kind}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%" title="${title}"></span>`;
  }).join('');
  let marker = '';
  const pos = daysBetween(from, today);
  if (!p.planned && pos >= 0 && pos < span) {
    marker = `<span class="mg-today" style="left:${(((pos + 0.5) / span) * 100).toFixed(3)}%" title="${i18n.t('rel.today')}"></span>`;
  }
  return `<div class="mg-stagebar${opts.large ? ' large' : ''}${p.planned ? ' planned' : ''}">${parts}${marker}</div>`;
}

// One line about what is next for a planting.
export function nextLine(i18n, p, today) {
  const c = p.computed;
  const lang = i18n.lang;
  if (p.planned) {
    const n = daysBetween(today, p.sown_on);
    return n <= 0 ? i18n.t('line.sow_now') : i18n.t('line.sow_on', { date: fmtDate(p.sown_on, lang), rel: relDays(i18n, n) });
  }
  if (c.status === 'ready') {
    const left = daysBetween(today, c.harvest_end);
    return left === 0 ? i18n.t('line.harvest_last_day') : i18n.t('line.harvest_until', { date: fmtDate(c.harvest_end, lang), count: left + 1 });
  }
  if (c.status === 'overdue') return i18n.t('line.overdue', { count: daysBetween(c.harvest_end, today) });
  return i18n.t('line.harvest_from', { date: fmtDate(c.harvest_start, lang), rel: relDays(i18n, c.days_to_harvest) });
}

export function waterLine(i18n, p, today) {
  const c = p.computed;
  if (p.planned || !c.water_due_on) return '';
  if (c.needs_water) {
    const late = daysBetween(c.water_due_on, today);
    return `<div class="mg-water due">${icon('mdi:water-alert')}${late > 0 ? i18n.t('line.water_late', { count: late }) : i18n.t('line.water_today')}</div>`;
  }
  const n = daysBetween(today, c.water_due_on);
  const watered = p.last_watered_on === today;
  return `<div class="mg-water">${icon('mdi:water-outline')}${watered ? i18n.t('line.watered_today') : i18n.t('line.water_next', { rel: relDays(i18n, n) })}</div>`;
}

// Buttons for what can be done to a planting now. data-act is handled by
// handleAction(); `compact` drops the labels.
export function actionButtons(i18n, snap, p, opts = {}) {
  const tasks = snap.tasksByPlanting.get(p.id) || [];
  const has = (k) => tasks.some((t) => t.kind === k);
  const btn = (act, ic, label, primary) => `<button type="button" class="mg-btn${primary ? ' primary' : ''}${opts.compact ? ' icon-only' : ''}" data-act="${act}" data-id="${esc(p.id)}" title="${label}" aria-label="${label}">${icon(ic)}${opts.compact ? '' : `<span>${label}</span>`}</button>`;
  const out = [];
  if (p.planned) {
    if (has('soak')) out.push(btn('soak', TASK_ICONS.soak, i18n.t('btn.soaked'), true));
    if (has('sow')) out.push(btn('sown', TASK_ICONS.sow, i18n.t('btn.sown'), true));
  } else {
    if (has('harvest')) out.push(btn('harvest', TASK_ICONS.harvest, i18n.t('btn.harvest'), true));
    if (has('uncover')) out.push(btn('uncover', TASK_ICONS.uncover, i18n.t('btn.uncover'), true));
    if (p.crop.water_every_days > 0) out.push(btn('water', TASK_ICONS.water, i18n.t('btn.water'), has('water')));
    if (!has('harvest') && (p.computed.status === 'growing' || p.computed.status === 'covered') && opts.all) {
      out.push(btn('harvest', TASK_ICONS.harvest, i18n.t('btn.harvest_early'), false));
    }
  }
  if (!opts.noDetails) out.push(btn('open', 'mdi:dots-horizontal', i18n.t('btn.details'), false));
  return `<div class="mg-actions">${out.join('')}</div>`;
}

// "Day 5 of 8"; past the grow time just "Day 16".
export function dayLine(i18n, c) {
  return c.day > c.total_days ? i18n.t('line.day', { day: c.day }) : i18n.t('line.day_of', { day: c.day, total: c.total_days });
}

export function plotTile(i18n, snap, plot, opts = {}) {
  const today = snap.today;
  const cur = plot.current ? snap.plantingById.get(plot.current) : null;
  const nxt = plot.next ? snap.plantingById.get(plot.next) : null;
  const head = `<div class="mg-tile-head"><div class="mg-tile-name"><span class="mg-tile-title">${esc(plot.name)}</span>${plot.location ? `<span class="mg-muted mg-small">${esc(plot.location)}</span>` : ''}</div>${statusPill(i18n, plot.status)}</div>`;
  if (!cur) {
    return `<div class="mg-tile mg-st-border-empty" data-plot="${esc(plot.id)}">${head}
      <div class="mg-empty-body">${icon('mdi:tray', 'mg-empty-ic')}<span class="mg-muted">${i18n.t('board.empty')}</span></div>
      <div class="mg-actions"><button type="button" class="mg-btn primary" data-act="sow" data-plot="${esc(plot.id)}">${icon('mdi:seed')}<span>${i18n.t('btn.sow')}</span></button></div></div>`;
  }
  const c = cur.computed;
  const day = cur.planned ? '' : `<span class="mg-muted mg-small">${dayLine(i18n, c)}</span>`;
  const nextPlan = nxt ? `<div class="mg-next mg-small">${icon('mdi:calendar-clock')}${i18n.t('line.next_plan', { crop: esc(nxt.crop.name), date: fmtDate(nxt.sown_on, i18n.lang) })}</div>` : '';
  return `<div class="mg-tile mg-st-border-${esc(c.status)}" data-plot="${esc(plot.id)}">${head}
    <div class="mg-crop-line" data-act="open" data-id="${esc(cur.id)}">${cropDot(cur.crop.color)}<span class="mg-crop-name">${esc(cur.crop.name)}</span>${cur.label ? `<span class="mg-muted mg-small">${esc(cur.label)}</span>` : ''}${day}</div>
    ${stageBar(i18n, cur, today)}
    <div class="mg-next-line">${nextLine(i18n, cur, today)}</div>
    ${opts.compact ? '' : waterLine(i18n, cur, today)}
    ${nextPlan}
    ${opts.actions === false ? '' : actionButtons(i18n, snap, cur, { compact: opts.compact })}
  </div>`;
}

export function taskList(i18n, snap, opts = {}) {
  const tasks = opts.plots ? snap.tasks.filter((t) => opts.plots.includes(t.plot_id)) : snap.tasks;
  if (!tasks.length) {
    return `<div class="mg-tasks-empty">${icon('mdi:check-circle-outline')}<span>${i18n.t('board.no_tasks')}</span></div>`;
  }
  const rows = tasks.map((t) => {
    const p = snap.plantingById.get(t.planting_id);
    const plot = snap.plotById.get(t.plot_id);
    if (!p || !plot) return '';
    let tag = '';
    if (t.last_day) tag = `<span class="mg-tag warn">${i18n.t('task.last_day')}</span>`;
    else if (t.late) tag = `<span class="mg-tag late">${i18n.t('task.late', { count: daysBetween(t.kind === 'harvest' ? p.computed.harvest_end : t.due_on, snap.today) })}</span>`;
    return `<li class="mg-task mg-task-${esc(t.kind)}">
      <button type="button" class="mg-check" data-act="task" data-task="${esc(t.id)}" title="${i18n.t('btn.done')}" aria-label="${i18n.t('btn.done')}">${icon(TASK_ICONS[t.kind] || 'mdi:check')}</button>
      <div class="mg-task-text" data-act="open" data-id="${esc(p.id)}"><span class="mg-task-kind">${i18n.t(`task.${t.kind}`)}</span><span>${cropDot(p.crop.color)}${esc(p.crop.name)} · ${esc(plot.name)}</span></div>${tag}</li>`;
  }).join('');
  const waterCount = tasks.filter((t) => t.kind === 'water').length;
  const waterAll = waterCount > 1 && opts.waterAll !== false
    ? `<button type="button" class="mg-btn" data-act="water-all">${icon(TASK_ICONS.water)}<span>${i18n.t('btn.water_all', { count: waterCount })}</span></button>`
    : '';
  return `<ul class="mg-tasks">${rows}</ul>${waterAll ? `<div class="mg-actions end">${waterAll}</div>` : ''}`;
}

export function timeline(i18n, snap, opts) {
  const { start, days } = opts;
  const rows = timelineRows(snap, start, days);
  const lang = i18n.lang;
  const todayPos = daysBetween(start, snap.today);
  const cols = [];
  for (let i = 0; i < days; i++) {
    const iso = addDays(start, i);
    const d = parseISO(iso);
    const weekend = d.getDay() === 0 || d.getDay() === 6;
    const month = d.getDate() === 1 || i === 0 ? fmtDate(iso, lang, { month: 'short' }) : '';
    cols.push(`<div class="mg-tl-day${weekend ? ' weekend' : ''}${iso === snap.today ? ' today' : ''}"><span class="mg-tl-month">${esc(month)}</span><span class="mg-tl-wd">${esc(fmtDate(iso, lang, { weekday: 'narrow' }))}</span><span class="mg-tl-dn">${d.getDate()}</span></div>`);
  }
  const grid = [];
  for (let i = 0; i < days; i++) {
    const d = parseISO(addDays(start, i));
    grid.push(`<div class="mg-tl-cell${d.getDay() === 0 || d.getDay() === 6 ? ' weekend' : ''}"></div>`);
  }
  const pct = (n) => ((n / days) * 100).toFixed(4);
  const frac = ((todayPos + 0.5) / days).toFixed(5);
  const todayLine = todayPos >= 0 && todayPos < days ? `<div class="mg-tl-now" style="left:calc(var(--mg-plot-w) + (100% - var(--mg-plot-w)) * ${frac})"></div>` : '';
  const body = rows.map((r) => {
    const bars = r.bars.map((b) => {
      const segs = b.segs.map((s) => `<span class="mg-seg mg-seg-${s.kind}" style="left:${((s.left / b.width) * 100).toFixed(3)}%;width:${((s.width / b.width) * 100).toFixed(3)}%"></span>`).join('');
      const title = `${b.name} · ${i18n.tt(b.type === 'history' ? `outcome.${b.status}` : `status.${b.status}`)}`;
      return `<button type="button" class="mg-tl-bar ${b.type}${b.clipStart ? ' clip-s' : ''}${b.clipEnd ? ' clip-e' : ''}" style="left:${pct(b.left)}%;width:${pct(b.width)}%" data-act="${b.type === 'history' ? 'history' : 'open'}" data-id="${esc(b.id)}" title="${esc(title)}">${segs}<span class="mg-tl-label">${cropDot(b.color)}${esc(b.name)}</span></button>`;
    }).join('');
    return `<div class="mg-tl-row"><div class="mg-tl-plot" title="${esc(r.plot.location || '')}">${esc(r.plot.name)}</div><div class="mg-tl-track" data-act="${opts.sow === false ? '' : 'tl-sow'}" data-plot="${esc(r.plot.id)}">${bars}</div></div>`;
  }).join('');
  return `<div class="mg-tl" style="--mg-days:${days}">
    <div class="mg-tl-scroll"><div class="mg-tl-inner">
      <div class="mg-tl-row mg-tl-header"><div class="mg-tl-plot"></div><div class="mg-tl-days">${cols.join('')}</div></div>
      <div class="mg-tl-body"><div class="mg-tl-grid">${grid.join('')}</div>${todayLine}${body}</div>
    </div></div>
    <div class="mg-legend">${['cover', 'light', 'window', 'late', 'past'].map((k) => `<span><span class="mg-legend-sw mg-seg-${k}"></span>${i18n.t(`legend.${k}`)}</span>`).join('')}</div>
  </div>`;
}

// --------------------------------------------------------------------------
// Dialogs and toasts (shared by panel and card)
// --------------------------------------------------------------------------

function rootOf(host) {
  return host.shadowRoot || host;
}

export function toast(host, text, opts = {}) {
  const root = rootOf(host);
  const old = root.querySelector('.mg-toast');
  if (old) old.remove();
  const el = document.createElement('div');
  el.className = `mg-toast${opts.error ? ' error' : ''}`;
  el.setAttribute('role', 'status');
  el.innerHTML = `<span>${esc(text)}</span>${opts.action ? `<button type="button" class="mg-toast-btn">${esc(opts.action)}</button>` : ''}`;
  if (opts.action) {
    el.querySelector('button').addEventListener('click', () => { el.remove(); opts.onAction && opts.onAction(); });
  }
  // Inside an open modal dialog the toast must be in the top layer too.
  const dlg = root.querySelector('dialog[open]');
  (dlg || root).appendChild(el);
  setTimeout(() => el.remove(), opts.ms || (opts.action ? 7000 : 3500));
}

export function openDialog(host, i18n, { title, body, wide, onReady }) {
  const root = rootOf(host);
  const dlg = document.createElement('dialog');
  dlg.className = `mg-dialog${wide ? ' wide' : ''}`;
  dlg.innerHTML = `<div class="mg-dlg-head"><h2>${title}</h2><button type="button" class="mg-icon-btn" data-close aria-label="${i18n.t('btn.close')}">${icon('mdi:close')}</button></div><div class="mg-dlg-body">${body}</div><div class="mg-dlg-error" hidden></div>`;
  root.appendChild(dlg);
  dlg.addEventListener('close', () => dlg.remove());
  dlg.addEventListener('click', (e) => {
    if (e.target === dlg) dlg.close();
    if (e.target.closest('[data-close]')) dlg.close();
  });
  dlg.showError = (err) => {
    const box = dlg.querySelector('.mg-dlg-error');
    box.textContent = typeof err === 'string' ? err : errorText(i18n, err);
    box.hidden = false;
  };
  dlg.showModal();
  if (onReady) onReady(dlg);
  return dlg;
}

// Run a backend call from a button: disabled while busy, errors shown.
export async function busy(btn, fn, onError) {
  if (btn) btn.disabled = true;
  try {
    return await fn();
  } catch (err) {
    if (onError) onError(err);
    return undefined;
  } finally {
    if (btn && btn.isConnected) btn.disabled = false;
  }
}

function fieldNum(name, label, value, min, max, hint) {
  return `<label class="mg-field"><span>${label}</span><input type="number" name="${name}" value="${esc(value)}" min="${min}" max="${max}" step="1" inputmode="numeric">${hint ? `<small>${hint}</small>` : ''}</label>`;
}

export function stageFields(i18n, v) {
  return `<div class="mg-grid-fields">
    ${fieldNum('cover_days', i18n.t('field.cover_days'), v.cover_days, 0, 90, i18n.t('hint.cover_days'))}
    ${fieldNum('light_days', i18n.t('field.light_days'), v.light_days, 1, 90, i18n.t('hint.light_days'))}
    ${fieldNum('harvest_window_days', i18n.t('field.harvest_window_days'), v.harvest_window_days, 1, 30, i18n.t('hint.harvest_window_days'))}
    ${fieldNum('water_every_days', i18n.t('field.water_every_days'), v.water_every_days, 0, 30, i18n.t('hint.water_every_days'))}
    ${fieldNum('soak_hours', i18n.t('field.soak_hours'), v.soak_hours, 0, 72, i18n.t('hint.soak_hours'))}
  </div>`;
}

export function readForm(root, names) {
  const out = {};
  for (const n of names) {
    const el = root.querySelector(`[name="${n}"]`);
    if (!el) continue;
    out[n] = el.type === 'checkbox' ? el.checked : el.value;
  }
  return out;
}

export function cropSummary(i18n, c) {
  const parts = [];
  if (c.soak_hours) parts.push(i18n.t('crop.soak', { count: c.soak_hours }));
  if (c.cover_days) parts.push(i18n.t('crop.cover', { count: c.cover_days }));
  parts.push(i18n.t('crop.light', { count: c.light_days }));
  parts.push(i18n.t('crop.window', { count: c.harvest_window_days }));
  parts.push(c.water_every_days ? i18n.t('crop.water', { count: c.water_every_days }) : i18n.t('crop.no_water'));
  return parts.join(' · ');
}

// ctx: { host, hass (getter), i18n, snap (getter) }
export function sowDialog(ctx, preset = {}) {
  const { i18n } = ctx;
  const snap = ctx.snap();
  if (!snap.profiles.length) { toast(ctx.host, i18n.tt('msg.no_crops'), { error: true }); return; }
  const date = preset.date || snap.today;
  const chosen = new Set(preset.plot ? [preset.plot] : snap.plots.filter((p) => p.status === 'empty').slice(0, 1).map((p) => p.id));
  const plots = snap.plots.map((p) => {
    const cur = p.current ? snap.plantingById.get(p.current) : null;
    const sub = cur ? `${esc(cur.crop.name)} · ${i18n.t(`status.${p.status}`)}` : i18n.t('status.empty');
    return `<label class="mg-chip-check"><input type="checkbox" name="plot" value="${esc(p.id)}"${chosen.has(p.id) ? ' checked' : ''}><span><b>${esc(p.name)}</b><small>${sub}</small></span></label>`;
  }).join('');
  const lastCrop = preset.profile || localStorage.getItem('ha_microgreens.last_crop');
  const first = snap.profileById.has(lastCrop) ? lastCrop : snap.profiles[0].id;
  const crops = snap.profiles.map((p) => `<option value="${esc(p.id)}"${p.id === first ? ' selected' : ''}>${esc(p.name)}</option>`).join('');
  const body = `<form class="mg-form" novalidate>
    <div class="mg-field"><span>${i18n.t('field.plots')}</span><div class="mg-chips">${plots}</div></div>
    <label class="mg-field"><span>${i18n.t('field.crop')}</span><select name="profile_id">${crops}</select><small class="mg-crop-sum"></small></label>
    <label class="mg-field"><span>${i18n.t('field.sown_on')}</span><input type="date" name="sown_on" value="${esc(date)}" required><small class="mg-plan-note"></small></label>
    <div class="mg-preview"></div>
    <details class="mg-more"><summary>${i18n.t('field.more')}</summary>
      <label class="mg-field"><span>${i18n.t('field.label')}</span><input type="text" name="label" maxlength="60" placeholder="${i18n.t('hint.label')}"></label>
      <label class="mg-field"><span>${i18n.t('field.notes')}</span><textarea name="notes" rows="2" maxlength="1000"></textarea></label>
    </details>
    <div class="mg-actions end"><button type="button" class="mg-btn" data-close>${i18n.t('btn.cancel')}</button><button type="submit" class="mg-btn primary">${icon('mdi:seed')}<span class="mg-submit-label">${i18n.t('btn.sow')}</span></button></div>
  </form>`;
  openDialog(ctx.host, i18n, {
    title: i18n.t('dialog.sow'),
    body,
    onReady: (dlg) => {
      const form = dlg.querySelector('form');
      const update = () => {
        const prof = ctx.snap().profileById.get(form.profile_id.value);
        const d = form.sown_on.value || snap.today;
        if (!prof) return;
        form.querySelector('.mg-crop-sum').innerHTML = cropSummary(i18n, prof);
        const pv = previewDates(prof, d);
        const lang = i18n.lang;
        form.querySelector('.mg-preview').innerHTML = `${cropDot(prof.color)}${i18n.t('dialog.sow_preview', { uncover: fmtDate(pv.uncover, lang), start: fmtDate(pv.start, lang), end: fmtDate(pv.end, lang) })}`;
        const planned = d > snap.today;
        form.querySelector('.mg-plan-note').innerHTML = planned ? i18n.t('hint.planned') : '';
        form.querySelector('.mg-submit-label').innerHTML = planned ? i18n.t('btn.plan') : i18n.t('btn.sow');
      };
      form.addEventListener('input', update);
      update();
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const plotIds = [...form.querySelectorAll('input[name="plot"]:checked')].map((x) => x.value);
        if (!plotIds.length) { dlg.showError(i18n.tt('error.no_plot')); return; }
        const btn = form.querySelector('[type="submit"]');
        busy(btn, async () => {
          await ws(ctx.hass(), 'planting/sow', { plot_ids: plotIds, profile_id: form.profile_id.value, sown_on: form.sown_on.value || null, label: form.label.value.trim(), notes: form.notes.value.trim() });
          localStorage.setItem('ha_microgreens.last_crop', form.profile_id.value);
          dlg.close();
          toast(ctx.host, i18n.tt(form.sown_on.value > snap.today ? 'msg.planned' : 'msg.sown', { count: plotIds.length }));
        }, (err) => dlg.showError(err));
      });
    },
  });
}

export function harvestDialog(ctx, plantingId) {
  const { i18n } = ctx;
  const snap = ctx.snap();
  const p = snap.plantingById.get(plantingId);
  if (!p) return;
  const plot = snap.plotById.get(p.plot_id);
  const stars = [1, 2, 3, 4, 5].map((n) => `<label class="mg-star"><input type="radio" name="rating" value="${n}"><span title="${n}">${icon('mdi:star')}</span></label>`).join('');
  const body = `<form class="mg-form" novalidate>
    <p class="mg-lead">${cropDot(p.crop.color)}${i18n.t('dialog.harvest_lead', { crop: p.crop.name, plot: plot ? plot.name : p.plot_id, count: Math.max(1, p.computed.day) })}</p>
    <div class="mg-grid-fields">
      <label class="mg-field"><span>${i18n.t('field.yield_grams')}</span><input type="number" name="yield_grams" min="0" step="0.1" inputmode="decimal" placeholder="0"></label>
      <label class="mg-field"><span>${i18n.t('field.ended_on')}</span><input type="date" name="ended_on" value="${esc(snap.today)}" min="${esc(p.sown_on)}" max="${esc(snap.today)}"></label>
    </div>
    <div class="mg-field"><span>${i18n.t('field.rating')}</span><div class="mg-stars">${stars}<button type="button" class="mg-link" data-clear-rating>${i18n.t('btn.clear')}</button></div></div>
    <label class="mg-field"><span>${i18n.t('field.notes')}</span><textarea name="notes" rows="2" maxlength="1000"></textarea></label>
    <div class="mg-actions end"><button type="button" class="mg-btn" data-close>${i18n.t('btn.cancel')}</button><button type="submit" class="mg-btn primary">${icon('mdi:content-cut')}<span>${i18n.t('btn.harvest')}</span></button></div>
  </form>`;
  openDialog(ctx.host, i18n, {
    title: i18n.t('dialog.harvest'),
    body,
    onReady: (dlg) => {
      const form = dlg.querySelector('form');
      form.querySelector('[data-clear-rating]').addEventListener('click', () => form.querySelectorAll('[name="rating"]').forEach((r) => { r.checked = false; }));
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const rating = form.querySelector('[name="rating"]:checked');
        const y = form.yield_grams.value;
        busy(form.querySelector('[type="submit"]'), async () => {
          const res = await ws(ctx.hass(), 'planting/action', {
            planting_id: p.id,
            action: 'harvest',
            yield_grams: y === '' ? null : Number(y),
            rating: rating ? Number(rating.value) : null,
            ended_on: form.ended_on.value || null,
            notes: form.notes.value.trim(),
          });
          dlg.close();
          undoToast(ctx, i18n.tt('msg.harvested', { plot: plot ? plot.name : p.plot_id }), res.history_id);
        }, (err) => dlg.showError(err));
      });
    },
  });
}

export function discardDialog(ctx, plantingId) {
  const { i18n } = ctx;
  const p = ctx.snap().plantingById.get(plantingId);
  if (!p) return;
  if (p.planned) {
    if (!confirm(i18n.tt('confirm.cancel_plan', { crop: p.crop.name }))) return;
    ws(ctx.hass(), 'planting/action', { planting_id: p.id, action: 'discard' })
      .then(() => toast(ctx.host, i18n.tt('msg.plan_cancelled')))
      .catch((err) => toast(ctx.host, errorText(i18n, err), { error: true }));
    return;
  }
  const reasons = REASONS.map((r) => `<option value="${r}">${i18n.t(`reason.${r}`)}</option>`).join('');
  const body = `<form class="mg-form" novalidate>
    <p class="mg-lead">${i18n.t('dialog.discard_lead', { crop: p.crop.name })}</p>
    <label class="mg-field"><span>${i18n.t('field.reason')}</span><select name="reason">${reasons}</select></label>
    <label class="mg-field"><span>${i18n.t('field.notes')}</span><textarea name="notes" rows="2" maxlength="1000"></textarea></label>
    <div class="mg-actions end"><button type="button" class="mg-btn" data-close>${i18n.t('btn.cancel')}</button><button type="submit" class="mg-btn danger">${icon('mdi:delete-outline')}<span>${i18n.t('btn.discard')}</span></button></div>
  </form>`;
  openDialog(ctx.host, i18n, {
    title: i18n.t('dialog.discard'),
    body,
    onReady: (dlg) => {
      const form = dlg.querySelector('form');
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        busy(form.querySelector('[type="submit"]'), async () => {
          const res = await ws(ctx.hass(), 'planting/action', { planting_id: p.id, action: 'discard', reason: form.reason.value, notes: form.notes.value.trim() });
          dlg.close();
          undoToast(ctx, i18n.tt('msg.discarded'), res.history_id);
        }, (err) => dlg.showError(err));
      });
    },
  });
}

function undoToast(ctx, text, historyId) {
  const { i18n } = ctx;
  toast(ctx.host, text, historyId ? {
    action: i18n.tt('btn.undo'),
    onAction: () => ws(ctx.hass(), 'history/reopen', { history_id: historyId })
      .then(() => toast(ctx.host, i18n.tt('msg.reopened')))
      .catch((err) => toast(ctx.host, errorText(i18n, err), { error: true })),
  } : {});
}

export function plantingDialog(ctx, plantingId) {
  const { i18n } = ctx;
  const snap = ctx.snap();
  const p = snap.plantingById.get(plantingId);
  if (!p) return;
  const plot = snap.plotById.get(p.plot_id);
  const c = p.computed;
  const lang = i18n.lang;
  const d = (iso) => (iso ? esc(fmtDate(iso, lang, { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })) : '-');
  const facts = [
    [i18n.t('field.plot'), esc(plot ? plot.name : p.plot_id)],
    [p.planned ? i18n.t('fact.sow_on') : i18n.t('fact.sown_on'), d(p.sown_on)],
    p.planned && c.soak_on ? [i18n.t('fact.soak_on'), `${d(c.soak_on)}${p.soaked_on ? ` · ${i18n.t('fact.done')}` : ''}`] : null,
    p.crop.cover_days ? [i18n.t('fact.uncover_on'), p.uncovered_on ? i18n.t('fact.uncovered', { date: fmtDate(p.uncovered_on, lang) }) : d(c.uncover_on)] : null,
    [i18n.t('fact.harvest'), i18n.t('fact.range', { from: fmtDate(c.harvest_start, lang), to: fmtDate(c.harvest_end, lang) })],
    !p.planned && p.crop.water_every_days ? [i18n.t('fact.water'), `${i18n.t('crop.water', { count: p.crop.water_every_days })}${p.last_watered_on ? ` · ${i18n.t('fact.last_watered', { date: fmtDate(p.last_watered_on, lang) })}` : ''}`] : null,
    p.label ? [i18n.t('field.label'), esc(p.label)] : null,
    p.notes ? [i18n.t('field.notes'), esc(p.notes).replace(/\n/g, '<br>')] : null,
  ].filter(Boolean).map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('');
  const shift = `<div class="mg-shift"><span class="mg-muted mg-small">${p.planned ? i18n.t('dialog.shift_sow') : i18n.t('dialog.shift_harvest')}</span>
    <button type="button" class="mg-btn" data-dact="shift" data-days="-1">${icon('mdi:minus')}<span>${i18n.t('btn.day')}</span></button>
    <button type="button" class="mg-btn" data-dact="shift" data-days="1">${icon('mdi:plus')}<span>${i18n.t('btn.day')}</span></button></div>`;
  const view = `<div class="mg-pd-view">
    <div class="mg-pd-head">${cropDot(p.crop.color)}<b>${esc(p.crop.name)}</b>${statusPill(i18n, c.status)}${p.planned ? '' : `<span class="mg-muted mg-small">${dayLine(i18n, c)}</span>`}</div>
    ${stageBar(i18n, p, snap.today, { large: true })}
    <div class="mg-next-line">${nextLine(i18n, p, snap.today)}</div>
    <dl class="mg-facts">${facts}</dl>
    ${actionButtons(i18n, snap, p, { all: true, noDetails: true })}
    ${shift}
    <div class="mg-actions spread">
      <button type="button" class="mg-btn danger" data-dact="discard">${icon(p.planned ? 'mdi:calendar-remove' : 'mdi:delete-outline')}<span>${p.planned ? i18n.t('btn.cancel_plan') : i18n.t('btn.discard')}</span></button>
      <button type="button" class="mg-btn" data-dact="edit">${icon('mdi:pencil')}<span>${i18n.t('btn.edit')}</span></button>
    </div></div>`;
  const plotOpts = snap.plots.map((x) => `<option value="${esc(x.id)}"${x.id === p.plot_id ? ' selected' : ''}>${esc(x.name)}</option>`).join('');
  const edit = `<form class="mg-form mg-pd-edit" hidden novalidate>
    <div class="mg-grid-fields">
      <label class="mg-field"><span>${i18n.t('field.crop_name')}</span><input type="text" name="crop_name" value="${esc(p.crop.name)}" maxlength="60" required></label>
      <label class="mg-field"><span>${i18n.t('field.plot')}</span><select name="plot_id">${plotOpts}</select></label>
      <label class="mg-field"><span>${p.planned ? i18n.t('fact.sow_on') : i18n.t('fact.sown_on')}</span><input type="date" name="sown_on" value="${esc(p.sown_on)}"${p.planned ? '' : ` max="${esc(snap.today)}"`}></label>
      <label class="mg-field"><span>${i18n.t('field.label')}</span><input type="text" name="label" value="${esc(p.label)}" maxlength="60"></label>
      ${p.planned ? '' : `<label class="mg-field"><span>${i18n.t('field.uncovered_on')}</span><input type="date" name="uncovered_on" value="${esc(p.uncovered_on || '')}" min="${esc(p.sown_on)}" max="${esc(snap.today)}"></label>
      <label class="mg-field"><span>${i18n.t('field.last_watered_on')}</span><input type="date" name="last_watered_on" value="${esc(p.last_watered_on || '')}" min="${esc(p.sown_on)}" max="${esc(snap.today)}"></label>`}
    </div>
    ${stageFields(i18n, p.crop)}
    <label class="mg-field"><span>${i18n.t('field.notes')}</span><textarea name="notes" rows="3" maxlength="1000">${esc(p.notes)}</textarea></label>
    <div class="mg-actions end"><button type="button" class="mg-btn" data-dact="view">${i18n.t('btn.back')}</button><button type="submit" class="mg-btn primary">${i18n.t('btn.save')}</button></div>
  </form>`;
  openDialog(ctx.host, i18n, {
    title: esc(plot ? plot.name : p.plot_id),
    body: view + edit,
    wide: true,
    onReady: (dlg) => {
      const viewEl = dlg.querySelector('.mg-pd-view');
      const form = dlg.querySelector('.mg-pd-edit');
      dlg.addEventListener('click', (e) => {
        const el = e.target.closest('[data-dact],[data-act]');
        if (!el || !dlg.contains(el)) return;
        if (el.dataset.act) {
          // Shared tray actions: run them, close this dialog unless one opened.
          e.stopPropagation();
          dlg.close();
          handleAction(ctx, el);
          return;
        }
        const act = el.dataset.dact;
        if (act === 'edit') { viewEl.hidden = true; form.hidden = false; form.crop_name.focus(); }
        if (act === 'view') { viewEl.hidden = false; form.hidden = true; }
        if (act === 'discard') { dlg.close(); discardDialog(ctx, p.id); }
        if (act === 'shift') {
          busy(el, async () => {
            await ws(ctx.hass(), 'planting/action', { planting_id: p.id, action: 'shift', days: Number(el.dataset.days) });
            dlg.close();
            plantingDialog(ctx, p.id);
          }, (err) => dlg.showError(err));
        }
      });
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const v = readForm(form, ['crop_name', 'plot_id', 'sown_on', 'label', 'notes', 'cover_days', 'light_days', 'harvest_window_days', 'water_every_days', 'soak_hours', 'uncovered_on', 'last_watered_on']);
        const changes = { crop_name: v.crop_name.trim(), plot_id: v.plot_id, sown_on: v.sown_on, label: v.label.trim(), notes: v.notes.trim() };
        for (const k of ['cover_days', 'light_days', 'harvest_window_days', 'water_every_days', 'soak_hours']) changes[k] = Number(v[k]);
        if (!p.planned) {
          changes.uncovered_on = v.uncovered_on || null;
          changes.last_watered_on = v.last_watered_on || null;
        }
        busy(form.querySelector('[type="submit"]'), async () => {
          await ws(ctx.hass(), 'planting/update', { planting_id: p.id, changes });
          dlg.close();
          toast(ctx.host, i18n.tt('msg.saved'));
        }, (err) => dlg.showError(err));
      });
    },
  });
}

// A finished planting: edit its record, put it back, or delete it.
export function historyDialog(ctx, historyId) {
  const { i18n } = ctx;
  const snap = ctx.snap();
  const h = (snap.history || []).find((x) => x.id === historyId);
  if (!h) return;
  const lang = i18n.lang;
  const isAdmin = !!(ctx.hass().user && ctx.hass().user.is_admin);
  const stars = [1, 2, 3, 4, 5].map((n) => `<label class="mg-star"><input type="radio" name="rating" value="${n}"${h.rating === n ? ' checked' : ''}><span title="${n}">${icon('mdi:star')}</span></label>`).join('');
  const reasons = REASONS.map((r) => `<option value="${r}"${h.reason === r ? ' selected' : ''}>${i18n.t(`reason.${r}`)}</option>`).join('');
  const harvested = h.outcome === 'harvested';
  const body = `<form class="mg-form" novalidate>
    <p class="mg-lead">${cropDot(h.crop.color)}<b>${esc(h.crop.name)}</b>&nbsp;·&nbsp;${esc(h.plot_name)}&nbsp;<span class="mg-pill mg-st-${harvested ? 'growing' : 'overdue'}">${i18n.t(`outcome.${h.outcome}`)}</span></p>
    <p class="mg-muted mg-small">${i18n.t('history.span', { from: fmtDate(h.sown_on, lang), to: fmtDate(h.ended_on, lang), count: daysBetween(h.sown_on, h.ended_on) })}${h.label ? ` · ${esc(h.label)}` : ''}</p>
    <div class="mg-grid-fields">
      ${harvested ? `<label class="mg-field"><span>${i18n.t('field.yield_grams')}</span><input type="number" name="yield_grams" min="0" step="0.1" value="${h.yield_grams == null ? '' : esc(h.yield_grams)}"></label>` : `<label class="mg-field"><span>${i18n.t('field.reason')}</span><select name="reason">${reasons}</select></label>`}
      <label class="mg-field"><span>${i18n.t('field.ended_on')}</span><input type="date" name="ended_on" value="${esc(h.ended_on)}" min="${esc(h.sown_on)}" max="${esc(snap.today)}"></label>
    </div>
    ${harvested ? `<div class="mg-field"><span>${i18n.t('field.rating')}</span><div class="mg-stars">${stars}<button type="button" class="mg-link" data-clear-rating>${i18n.t('btn.clear')}</button></div></div>` : ''}
    <label class="mg-field"><span>${i18n.t('field.notes')}</span><textarea name="notes" rows="3" maxlength="1000">${esc(h.notes)}</textarea></label>
    <div class="mg-actions spread">
      <span class="mg-actions" style="margin:0">
        <button type="button" class="mg-btn" data-hact="reopen" title="${i18n.t('hint.reopen')}">${icon('mdi:undo')}<span>${i18n.t('btn.reopen')}</span></button>
        ${isAdmin ? `<button type="button" class="mg-btn danger" data-hact="delete">${icon('mdi:delete-outline')}<span>${i18n.t('btn.delete')}</span></button>` : ''}
      </span>
      <button type="submit" class="mg-btn primary">${i18n.t('btn.save')}</button>
    </div>
  </form>`;
  openDialog(ctx.host, i18n, {
    title: i18n.t('dialog.history'),
    body,
    onReady: (dlg) => {
      const form = dlg.querySelector('form');
      const clear = form.querySelector('[data-clear-rating]');
      if (clear) clear.addEventListener('click', () => form.querySelectorAll('[name="rating"]').forEach((r) => { r.checked = false; }));
      form.addEventListener('click', (e) => {
        const el = e.target.closest('[data-hact]');
        if (!el) return;
        if (el.dataset.hact === 'reopen') {
          busy(el, async () => { await ws(ctx.hass(), 'history/reopen', { history_id: h.id }); dlg.close(); toast(ctx.host, i18n.tt('msg.reopened')); }, (err) => dlg.showError(err));
        }
        if (el.dataset.hact === 'delete' && confirm(i18n.tt('confirm.delete_history'))) {
          busy(el, async () => { await ws(ctx.hass(), 'history/delete', { history_id: h.id }); dlg.close(); toast(ctx.host, i18n.tt('msg.deleted')); }, (err) => dlg.showError(err));
        }
      });
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const changes = { notes: form.notes.value.trim(), ended_on: form.ended_on.value };
        if (harvested) {
          const r = form.querySelector('[name="rating"]:checked');
          changes.rating = r ? Number(r.value) : null;
          changes.yield_grams = form.yield_grams.value === '' ? null : Number(form.yield_grams.value);
        } else {
          changes.reason = form.reason.value;
        }
        busy(form.querySelector('[type="submit"]'), async () => {
          await ws(ctx.hass(), 'history/update', { history_id: h.id, changes });
          dlg.close();
          toast(ctx.host, i18n.tt('msg.saved'));
        }, (err) => dlg.showError(err));
      });
    },
  });
}

// The tray actions every view shares: data-act on a clicked element.
export async function handleAction(ctx, el) {
  const { i18n } = ctx;
  const act = el.dataset.act;
  const id = el.dataset.id;
  const snap = ctx.snap();
  const run = (fn, msg) => busy(el, async () => { await fn(); if (msg) toast(ctx.host, msg); }, (err) => toast(ctx.host, errorText(i18n, err), { error: true }));
  const plotName = (pid) => { const p = snap.plantingById.get(pid); const pl = p && snap.plotById.get(p.plot_id); return pl ? pl.name : ''; };
  switch (act) {
    case 'open': return plantingDialog(ctx, id);
    case 'sow': return sowDialog(ctx, { plot: el.dataset.plot, date: el.dataset.date });
    case 'harvest': return harvestDialog(ctx, id);
    case 'discard': return discardDialog(ctx, id);
    case 'history': return historyDialog(ctx, id);
    case 'water': return run(() => ws(ctx.hass(), 'planting/action', { planting_id: id, action: 'water' }), i18n.tt('msg.watered', { plot: plotName(id) }));
    case 'uncover': return run(() => ws(ctx.hass(), 'planting/action', { planting_id: id, action: 'uncover' }), i18n.tt('msg.uncovered', { plot: plotName(id) }));
    case 'soak': return run(() => ws(ctx.hass(), 'planting/action', { planting_id: id, action: 'soak' }), i18n.tt('msg.soaked'));
    case 'sown': return run(() => ws(ctx.hass(), 'planting/action', { planting_id: id, action: 'sow' }), i18n.tt('msg.sown', { count: 1 }));
    case 'water-all': return run(async () => {
      const res = await ws(ctx.hass(), 'water', {});
      toast(ctx.host, i18n.tt('msg.watered_n', { count: res.watered }));
    });
    case 'task': {
      const [kind, pid] = String(el.dataset.task).split(':');
      if (kind === 'harvest') return harvestDialog(ctx, pid);
      const msgs = { water: i18n.tt('msg.watered', { plot: plotName(pid) }), uncover: i18n.tt('msg.uncovered', { plot: plotName(pid) }), sow: i18n.tt('msg.sown', { count: 1 }), soak: i18n.tt('msg.soaked') };
      return run(() => ws(ctx.hass(), 'task/complete', { task_id: el.dataset.task }), msgs[kind]);
    }
    default: return undefined;
  }
}

// --------------------------------------------------------------------------
// Styles (shared; the panel and the card add their own layout)
// --------------------------------------------------------------------------

export const STYLES = `
:host{--mg-covered:#5c6bc0;--mg-growing:#43a047;--mg-ready:#f9a825;--mg-overdue:#e53935;--mg-planned:#90a4ae;--mg-soak:#4fc3f7;--mg-empty:var(--disabled-text-color,#9e9e9e);--mg-radius:var(--ha-card-border-radius,12px);--mg-gap:12px}
*{box-sizing:border-box}
[hidden]{display:none!important}
.mg-muted{color:var(--secondary-text-color)}
.mg-small{font-size:12px}
.mg-ic{--mdc-icon-size:18px;width:18px;height:18px;flex:none}
.mg-dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;flex:none;vertical-align:middle}
.mg-pill{display:inline-flex;align-items:center;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;color:#fff;background:var(--mg-empty)}
.mg-pill.mg-st-empty{background:transparent;color:var(--secondary-text-color);border:1px solid var(--divider-color)}
.mg-pill.mg-st-planned{background:var(--mg-planned)}
.mg-pill.mg-st-covered{background:var(--mg-covered)}
.mg-pill.mg-st-growing{background:var(--mg-growing)}
.mg-pill.mg-st-ready{background:var(--mg-ready);color:#3e2723}
.mg-pill.mg-st-overdue{background:var(--mg-overdue)}
.mg-tag{font-size:11px;padding:1px 8px;border-radius:999px;white-space:nowrap;font-weight:600}
.mg-tag.warn{background:color-mix(in srgb,var(--mg-ready) 25%,transparent);color:var(--primary-text-color)}
.mg-tag.late{background:color-mix(in srgb,var(--mg-overdue) 18%,transparent);color:var(--mg-overdue)}
.mg-btn{display:inline-flex;align-items:center;gap:6px;min-height:34px;padding:6px 12px;border-radius:10px;border:1px solid var(--divider-color);background:var(--secondary-background-color,transparent);color:var(--primary-text-color);font:inherit;font-size:13px;font-weight:500;cursor:pointer;transition:filter .12s,transform .06s}
.mg-btn:hover{filter:brightness(1.06)}
.mg-btn:active{transform:translateY(1px)}
.mg-btn:disabled{opacity:.55;cursor:progress}
.mg-btn.primary{background:var(--primary-color);border-color:var(--primary-color);color:var(--text-primary-color,#fff)}
.mg-btn.danger{color:var(--error-color,#db4437);border-color:color-mix(in srgb,var(--error-color,#db4437) 45%,transparent);background:transparent}
.mg-btn.icon-only{padding:6px 8px}
.mg-btn:focus-visible,.mg-check:focus-visible,.mg-icon-btn:focus-visible,.mg-tl-bar:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
.mg-icon-btn{display:inline-flex;align-items:center;justify-content:center;width:36px;height:36px;border-radius:50%;border:none;background:transparent;color:var(--primary-text-color);cursor:pointer}
.mg-icon-btn:hover{background:var(--secondary-background-color)}
.mg-link{border:none;background:none;color:var(--primary-color);cursor:pointer;font:inherit;font-size:12px;padding:0 4px}
.mg-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:10px}
.mg-actions.end{justify-content:flex-end}
.mg-actions.spread{justify-content:space-between}
/* stage bar */
.mg-stagebar{position:relative;height:10px;border-radius:999px;background:var(--divider-color);overflow:hidden;margin:10px 0 6px}
.mg-stagebar.large{height:16px}
.mg-stagebar.planned{opacity:.6}
.mg-seg{position:absolute;top:0;bottom:0}
.mg-seg-soak{background:var(--mg-soak)}
.mg-seg-cover{background:var(--mg-covered)}
.mg-seg-light{background:var(--mg-growing)}
.mg-seg-window{background:var(--mg-ready)}
.mg-seg-late{background:repeating-linear-gradient(45deg,var(--mg-overdue) 0 6px,color-mix(in srgb,var(--mg-overdue) 55%,transparent) 6px 12px)}
.mg-seg-past{background:color-mix(in srgb,var(--mg-growing) 35%,var(--divider-color))}
.mg-seg-failed{background:repeating-linear-gradient(45deg,var(--divider-color) 0 5px,transparent 5px 10px)}
.mg-today{position:absolute;top:-3px;bottom:-3px;width:3px;margin-left:-1.5px;background:var(--primary-text-color);border-radius:2px;box-shadow:0 0 0 2px var(--card-background-color,#fff)}
/* tiles */
.mg-tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:var(--mg-gap)}
.mg-tile{position:relative;padding:14px;border-radius:var(--mg-radius);background:var(--card-background-color,#fff);border:1px solid var(--divider-color);border-left:5px solid var(--mg-empty);display:flex;flex-direction:column;min-width:0}
.mg-st-border-planned{border-left-color:var(--mg-planned)}
.mg-st-border-covered{border-left-color:var(--mg-covered)}
.mg-st-border-growing{border-left-color:var(--mg-growing)}
.mg-st-border-ready{border-left-color:var(--mg-ready)}
.mg-st-border-overdue{border-left-color:var(--mg-overdue)}
.mg-st-border-empty{border-left-style:dashed}
.mg-tile-head{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}
.mg-tile-name{display:flex;flex-direction:column;min-width:0}
.mg-tile-title{font-weight:700;font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mg-crop-line{display:flex;align-items:center;gap:6px;margin-top:8px;cursor:pointer;flex-wrap:wrap}
.mg-crop-name{font-weight:600}
.mg-next-line{font-size:13px}
.mg-water{display:flex;align-items:center;gap:6px;font-size:13px;margin-top:4px;color:var(--secondary-text-color)}
.mg-water.due{color:var(--info-color,#039be5);font-weight:600}
.mg-next{display:flex;align-items:center;gap:6px;margin-top:6px;color:var(--secondary-text-color)}
.mg-empty-body{display:flex;align-items:center;gap:10px;margin:14px 0 4px}
.mg-empty-ic{--mdc-icon-size:26px;width:26px;height:26px;color:var(--disabled-text-color)}
.mg-tile .mg-actions{margin-top:auto;padding-top:10px}
/* tasks */
.mg-tasks{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.mg-task{display:flex;align-items:center;gap:10px;padding:6px 8px;border-radius:10px;background:var(--secondary-background-color,rgba(0,0,0,.03))}
.mg-check{flex:none;display:inline-flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:50%;border:2px solid var(--primary-color);background:transparent;color:var(--primary-color);cursor:pointer}
.mg-check:hover{background:var(--primary-color);color:var(--text-primary-color,#fff)}
.mg-task-harvest .mg-check{border-color:var(--mg-ready);color:var(--mg-ready)}
.mg-task-harvest .mg-check:hover{background:var(--mg-ready);color:#3e2723}
.mg-task-uncover .mg-check{border-color:var(--mg-covered);color:var(--mg-covered)}
.mg-task-uncover .mg-check:hover{background:var(--mg-covered);color:#fff}
.mg-task-water .mg-check{border-color:var(--info-color,#039be5);color:var(--info-color,#039be5)}
.mg-task-water .mg-check:hover{background:var(--info-color,#039be5);color:#fff}
.mg-task-text{flex:1;display:flex;flex-direction:column;min-width:0;cursor:pointer}
.mg-task-kind{font-weight:600;font-size:13px}
.mg-task-text>span:last-child{font-size:13px;color:var(--secondary-text-color);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mg-tasks-empty{display:flex;align-items:center;gap:8px;color:var(--secondary-text-color);padding:6px 0}
.mg-tasks-empty .mg-ic{color:var(--success-color,#43a047)}
/* timeline */
.mg-tl{--mg-plot-w:110px;--mg-day-w:minmax(26px,1fr)}
.mg-tl-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.mg-tl-inner{min-width:calc(var(--mg-plot-w) + var(--mg-days) * 26px);position:relative}
.mg-tl-row{display:grid;grid-template-columns:var(--mg-plot-w) 1fr;align-items:stretch;min-height:38px;border-bottom:1px solid var(--divider-color)}
.mg-tl-header{position:sticky;top:0;z-index:2;background:var(--card-background-color,#fff);min-height:50px}
.mg-tl-plot{display:flex;align-items:center;padding:0 8px;font-weight:600;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;position:sticky;left:0;background:var(--card-background-color,#fff);z-index:1}
.mg-tl-days{display:grid;grid-template-columns:repeat(var(--mg-days),1fr)}
.mg-tl-day{display:flex;flex-direction:column;align-items:center;justify-content:flex-end;font-size:11px;line-height:14px;color:var(--secondary-text-color);padding:16px 0 4px;position:relative}
.mg-tl-day.weekend{background:color-mix(in srgb,var(--divider-color) 35%,transparent)}
.mg-tl-day.today .mg-tl-dn{background:var(--primary-color);color:var(--text-primary-color,#fff);border-radius:999px;padding:0 5px}
.mg-tl-month{position:absolute;top:2px;left:2px;line-height:12px;font-weight:700;text-transform:uppercase;font-size:10px;white-space:nowrap;color:var(--primary-text-color)}
.mg-tl-dn{font-weight:600;color:var(--primary-text-color)}
.mg-tl-body{position:relative}
.mg-tl-grid{position:absolute;inset:0 0 0 var(--mg-plot-w);display:grid;grid-template-columns:repeat(var(--mg-days),1fr);pointer-events:none}
.mg-tl-cell{border-left:1px solid color-mix(in srgb,var(--divider-color) 50%,transparent)}
.mg-tl-cell.weekend{background:color-mix(in srgb,var(--divider-color) 35%,transparent)}
.mg-tl-now{position:absolute;top:0;bottom:0;width:2px;margin-left:-1px;background:var(--primary-color);z-index:1;pointer-events:none;opacity:.8}
.mg-tl-track{position:relative;cursor:copy}
.mg-tl-track[data-act=""]{cursor:default}
.mg-tl-bar{position:absolute;top:6px;bottom:6px;border:none;padding:0;border-radius:8px;overflow:hidden;cursor:pointer;background:var(--divider-color);display:flex;align-items:center;box-shadow:0 1px 2px rgba(0,0,0,.18)}
.mg-tl-bar.history{opacity:.8;box-shadow:none}
.mg-tl-bar.clip-s{border-top-left-radius:0;border-bottom-left-radius:0}
.mg-tl-bar.clip-e{border-top-right-radius:0;border-bottom-right-radius:0}
.mg-tl-label{position:relative;z-index:1;display:flex;align-items:center;padding:0 8px;font-size:12px;font-weight:600;color:#fff;text-shadow:0 1px 2px rgba(0,0,0,.55);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.mg-tl-bar.history .mg-tl-label{color:var(--primary-text-color);text-shadow:none}
.mg-tl-label .mg-dot{box-shadow:0 0 0 2px rgba(255,255,255,.8)}
.mg-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:10px;font-size:12px;color:var(--secondary-text-color)}
.mg-legend>span{display:inline-flex;align-items:center;gap:6px}
.mg-legend-sw{display:inline-block;width:18px;height:10px;border-radius:3px;position:relative}
/* dialogs */
dialog.mg-dialog{border:none;border-radius:16px;padding:0;width:min(520px,calc(100vw - 24px));max-height:calc(100vh - 32px);background:var(--card-background-color,#fff);color:var(--primary-text-color);box-shadow:0 12px 40px rgba(0,0,0,.35);font-family:var(--paper-font-body1_-_font-family,inherit)}
dialog.mg-dialog.wide{width:min(680px,calc(100vw - 24px))}
dialog.mg-dialog::backdrop{background:rgba(0,0,0,.45)}
.mg-dlg-head{display:flex;align-items:center;justify-content:space-between;padding:14px 12px 6px 20px;position:sticky;top:0;background:inherit;z-index:1}
.mg-dlg-head h2{margin:0;font-size:19px;font-weight:600}
.mg-dlg-body{padding:4px 20px 20px}
.mg-dlg-error{margin:0 20px 16px;padding:10px 12px;border-radius:10px;background:color-mix(in srgb,var(--error-color,#db4437) 14%,transparent);color:var(--error-color,#db4437);font-size:13px}
.mg-form{display:flex;flex-direction:column;gap:12px}
.mg-field{display:flex;flex-direction:column;gap:4px;font-size:13px;min-width:0}
.mg-field>span{font-weight:600;color:var(--secondary-text-color);font-size:12px}
.mg-field small{color:var(--secondary-text-color);font-size:11.5px}
.mg-field input,.mg-field select,.mg-field textarea{font:inherit;font-size:14px;padding:9px 10px;border-radius:10px;border:1px solid var(--divider-color);background:var(--secondary-background-color,transparent);color:var(--primary-text-color);width:100%}
.mg-field input:focus,.mg-field select:focus,.mg-field textarea:focus{outline:2px solid var(--primary-color);outline-offset:-1px}
.mg-field input[type=color]{padding:2px;height:40px}
.mg-grid-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.mg-chips{display:flex;flex-wrap:wrap;gap:8px}
.mg-chip-check{position:relative;cursor:pointer}
.mg-chip-check input{position:absolute;opacity:0;pointer-events:none}
.mg-chip-check>span{display:flex;flex-direction:column;padding:6px 12px;border-radius:12px;border:1px solid var(--divider-color);min-width:84px}
.mg-chip-check>span small{color:var(--secondary-text-color);font-size:11px}
.mg-chip-check input:checked+span{border-color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 14%,transparent);box-shadow:inset 0 0 0 1px var(--primary-color)}
.mg-chip-check input:focus-visible+span{outline:2px solid var(--primary-color)}
.mg-preview{display:flex;align-items:center;font-size:13px;padding:8px 12px;border-radius:10px;background:var(--secondary-background-color,rgba(0,0,0,.04))}
.mg-more summary{cursor:pointer;color:var(--primary-color);font-size:13px;margin-bottom:8px}
.mg-more[open]{display:flex;flex-direction:column;gap:12px}
.mg-lead{margin:0;display:flex;align-items:center;flex-wrap:wrap}
.mg-stars{display:flex;align-items:center;gap:2px}
.mg-star input{position:absolute;opacity:0}
.mg-star span{cursor:pointer;color:var(--disabled-text-color,#bbb)}
.mg-star span .mg-ic{--mdc-icon-size:28px;width:28px;height:28px}
.mg-stars:has(.mg-star:nth-child(1) input:checked) .mg-star:nth-child(-n+1) span,
.mg-stars:has(.mg-star:nth-child(2) input:checked) .mg-star:nth-child(-n+2) span,
.mg-stars:has(.mg-star:nth-child(3) input:checked) .mg-star:nth-child(-n+3) span,
.mg-stars:has(.mg-star:nth-child(4) input:checked) .mg-star:nth-child(-n+4) span,
.mg-stars:has(.mg-star:nth-child(5) input:checked) .mg-star:nth-child(-n+5) span{color:var(--mg-ready)}
.mg-pd-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mg-facts{display:grid;grid-template-columns:max-content 1fr;gap:6px 16px;margin:14px 0 4px;font-size:13px}
.mg-facts dt{color:var(--secondary-text-color)}
.mg-facts dd{margin:0}
.mg-shift{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}
.mg-shift>span{margin-right:auto}
/* toast */
.mg-toast{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:20;display:flex;align-items:center;gap:14px;max-width:calc(100vw - 32px);padding:12px 16px;border-radius:12px;background:var(--primary-text-color,#212121);color:var(--card-background-color,#fff);box-shadow:0 6px 24px rgba(0,0,0,.3);font-size:14px;animation:mg-up .18s ease-out}
.mg-toast.error{background:var(--error-color,#db4437);color:#fff}
.mg-toast-btn{border:none;background:none;color:var(--primary-color);font:inherit;font-weight:700;cursor:pointer;text-transform:uppercase;font-size:13px}
.mg-toast.error .mg-toast-btn{color:#fff}
@keyframes mg-up{from{opacity:0;transform:translate(-50%,8px)}to{opacity:1;transform:translate(-50%,0)}}
@media (prefers-reduced-motion:reduce){.mg-toast{animation:none}.mg-btn{transition:none}}
`;
