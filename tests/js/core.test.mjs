// Unit tests for www/ha-microgreens-core.js, run by tests/test_js.py (node).
// The module is copied to a temp .mjs first, so node loads it as ESM on any
// version. Run TZ=Europe/Prague so the DST cases mean something.
import assert from 'node:assert/strict';
import { copyFileSync, mkdtempSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const www = join(here, '..', '..', 'custom_components', 'ha_microgreens', 'www');
const tmp = mkdtempSync(join(tmpdir(), 'mg-core-'));
copyFileSync(join(www, 'ha-microgreens-core.js'), join(tmp, 'core.mjs'));
const core = await import(pathToFileURL(join(tmp, 'core.mjs')).href);
const en = JSON.parse(readFileSync(join(www, 'i18n', 'en.json'), 'utf8'));

const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const planting = (over = {}) => ({
  id: 'p1',
  plot_id: 'A1',
  planned: false,
  sown_on: '2026-10-01',
  crop: { name: 'Radish', color: '#e53935', cover_days: 3, light_days: 5, harvest_window_days: 3, water_every_days: 1, soak_hours: 0 },
  computed: { status: 'covered', soak_on: null, uncover_on: '2026-10-04', harvest_start: '2026-10-09', harvest_end: '2026-10-11', total_days: 8, day: 1, progress: 0, water_due_on: '2026-10-02', needs_water: false, days_to_harvest: 8 },
  ...over,
});

test('esc escapes markup and quotes', () => {
  assert.equal(core.esc(`<a href="x" onclick='y'>&</a>`), '&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;&lt;/a&gt;');
  assert.equal(core.esc(null), '');
});

test('safeColor lets only #rrggbb through', () => {
  assert.equal(core.safeColor('#43A047'), '#43A047');
  assert.equal(core.safeColor('red;background:url(x)'), '#43a047');
});

test('I18n: plurals, fallback to English, escaping', () => {
  const i18n = new core.I18n('cs', { 'rel.in_days_few': 'za {count} dny', 'x.mark': '<b>{v}</b>' }, en);
  assert.equal(i18n.tt('rel.in_days', { count: 3 }), 'za 3 dny');
  assert.equal(i18n.tt('rel.in_days', { count: 5 }), 'in 5 days'); // cs "many/other" missing: English
  assert.equal(i18n.tt('nope.key'), 'nope.key');
  assert.equal(i18n.t('x.mark', { v: '<i>' }), '&lt;b&gt;&lt;i&gt;&lt;/b&gt;');
  const e = new core.I18n('en', {}, en);
  assert.equal(e.tt('rel.in_days', { count: 1 }), 'in 1 day');
  assert.equal(e.tt('crop.soak', { count: 12 }), 'soak 12 h'); // no plural forms: plain key
  assert.ok(e.has('task.late'));
});

test('dates stay local across the DST change', () => {
  assert.equal(core.addDays('2026-03-28', 2), '2026-03-30');
  assert.equal(core.daysBetween('2026-03-28', '2026-03-30'), 2);
  assert.equal(core.daysBetween('2026-10-24', '2026-10-26'), 2);
  assert.equal(core.addDays('2026-12-31', 1), '2027-01-01');
  assert.equal(core.toISO(core.parseISO('2026-02-28')), '2026-02-28');
});

test('relDays', () => {
  const e = new core.I18n('en', {}, en);
  assert.equal(core.relDays(e, 0), 'Today');
  assert.equal(core.relDays(e, 1), 'tomorrow');
  assert.equal(core.relDays(e, -3), '3 days ago');
});

test('stageSegments: cover, light, window', () => {
  const segs = core.stageSegments(planting(), '2026-10-02');
  assert.deepEqual(segs.map((s) => [s.kind, s.from, s.to]), [
    ['cover', '2026-10-01', '2026-10-04'],
    ['light', '2026-10-04', '2026-10-09'],
    ['window', '2026-10-09', '2026-10-12'],
  ]);
});

test('stageSegments: late tail grows to today, planned soak shows', () => {
  const late = core.stageSegments(planting(), '2026-10-14');
  assert.deepEqual(late.at(-1), { kind: 'late', from: '2026-10-12', to: '2026-10-15' });
  const plan = planting({ planned: true, computed: { ...planting().computed, soak_on: '2026-09-30' } });
  assert.equal(core.stageSegments(plan, '2026-09-20')[0].kind, 'soak');
  const noCover = planting({ crop: { ...planting().crop, cover_days: 0 }, computed: { ...planting().computed, uncover_on: '2026-10-01' } });
  assert.equal(core.stageSegments(noCover, '2026-10-02')[0].kind, 'light');
});

test('timelineRows clips bars to the range', () => {
  const snap = {
    today: '2026-10-05',
    plots: [{ id: 'A1', name: 'A1' }, { id: 'A2', name: 'A2' }],
    plantings: [planting()],
    history: [{ id: 'h1', plot_id: 'A2', outcome: 'harvested', sown_on: '2026-09-20', ended_on: '2026-10-04', crop: { name: 'Pea', color: '#43a047' } }],
  };
  const rows = core.timelineRows(snap, '2026-10-03', 7);
  const bar = rows[0].bars[0];
  assert.equal(bar.left, 0);
  assert.equal(bar.width, 7);
  assert.ok(bar.clipStart && bar.clipEnd);
  assert.deepEqual(bar.segs.map((s) => [s.kind, s.left, s.width]), [['cover', 0, 1], ['light', 1, 5], ['window', 6, 1]]);
  const past = rows[1].bars[0];
  // Harvested on 10-04: the bar covers 10-03 and 10-04, cut at the range start.
  assert.deepEqual([past.type, past.left, past.width, past.clipStart, past.segs[0].kind], ['history', 0, 2, true, 'past']);
});

test('timelineRows: history ending before the range is dropped', () => {
  const snap = { today: '2026-10-05', plots: [{ id: 'A2', name: 'A2' }], plantings: [], history: [{ id: 'h', plot_id: 'A2', outcome: 'discarded', sown_on: '2026-09-01', ended_on: '2026-09-10', crop: { name: 'X', color: '#000000' } }] };
  assert.equal(core.timelineRows(snap, '2026-10-01', 7)[0].bars.length, 0);
});

test('previewDates matches the backend stage model', () => {
  assert.deepEqual(core.previewDates({ cover_days: 3, light_days: 5, harvest_window_days: 3 }, '2026-10-01'), { uncover: '2026-10-04', start: '2026-10-09', end: '2026-10-11' });
});

test('cropStats aggregates per crop', () => {
  const crop = { name: 'Radish', color: '#e53935' };
  const stats = core.cropStats([
    { profile_id: 'radish', crop, outcome: 'harvested', sown_on: '2026-10-01', ended_on: '2026-10-09', yield_grams: 200, rating: 4 },
    { profile_id: 'radish', crop, outcome: 'harvested', sown_on: '2026-10-02', ended_on: '2026-10-12', yield_grams: 100, rating: null },
    { profile_id: 'radish', crop, outcome: 'discarded', sown_on: '2026-10-03', ended_on: '2026-10-05', yield_grams: null, rating: null },
  ]);
  assert.equal(stats.length, 1);
  const s = stats[0];
  assert.equal(s.trays, 3);
  assert.equal(s.avgYield, 150);
  assert.equal(s.totalYield, 300);
  assert.equal(s.avgDays, 9);
  assert.equal(s.avgRating, 4);
  assert.equal(Math.round(s.successRate * 100), 67);
});

test('errorText localises the code and the field', () => {
  const e = new core.I18n('en', {}, en);
  assert.equal(core.errorText(e, { code: 'plot_busy', translation_placeholders: { plot: 'Plot A1', crop: 'Pea', start: 's', end: 'e' } }), 'Plot A1 is taken by Pea from s to e.');
  // ISO dates in placeholders are shown in the user's format.
  assert.equal(core.errorText(e, { code: 'plot_busy', translation_placeholders: { plot: 'A1', crop: 'Pea', start: '2026-10-20', end: '2026-11-01' } }), 'A1 is taken by Pea from Oct 20 to Nov 1.');
  assert.equal(core.errorText(e, { code: 'invalid_number', translation_placeholders: { field: 'light_days', min: '1', max: '90' } }), 'Light (days) must be a whole number from 1 to 90.');
  assert.equal(core.errorText(e, { code: 'weird', message: 'raw' }), 'raw');
});

test('rendering escapes user text', () => {
  const e = new core.I18n('en', {}, en);
  const snap = core.indexSnapshot({
    today: '2026-10-02',
    plots: [{ id: 'A1', name: '<img src=x>', location: '', status: 'covered', current: 'p1', next: null }],
    profiles: [],
    plantings: [planting({ crop: { ...planting().crop, name: '<script>' }, label: '"x"' })],
    tasks: [{ id: 'water:p1', kind: 'water', planting_id: 'p1', plot_id: 'A1', due_on: '2026-10-02', late: false, last_day: false }],
    history: [],
  });
  const html = core.plotTile(e, snap, snap.plots[0]) + core.taskList(e, snap) + core.timeline(e, snap, { start: '2026-10-01', days: 14 });
  assert.ok(!html.includes('<script>'));
  assert.ok(!html.includes('<img src=x>'));
  assert.ok(html.includes('&lt;script&gt;'));
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    await fn();
    console.log(`ok   ${name}`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL ${name}\n     ${err && err.stack ? err.stack.split('\n').slice(0, 3).join('\n     ') : err}`);
  }
}
console.log(`${tests.length - failed}/${tests.length} passed`);
process.exit(failed ? 1 : 0);
