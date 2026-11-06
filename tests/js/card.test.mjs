// Load-order test for www/ha-microgreens-card.js, run by tests/test_js.py (node).
// HA's app bundle swaps window.customElements for a scoped-registry polyfill
// while this extra module may already be running; the card must be defined in
// the registry the dashboard sees after the swap.
import assert from 'node:assert/strict';
import { copyFileSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const www = join(here, '..', '..', 'custom_components', 'ha_microgreens', 'www');
const tmp = mkdtempSync(join(tmpdir(), 'mg-card-'));
for (const f of ['ha-microgreens-card.js', 'ha-microgreens-core.js']) copyFileSync(join(www, f), join(tmp, f));
writeFileSync(join(tmp, 'package.json'), '{"type":"module"}');

function registry() {
  const defs = new Map();
  const waiting = new Map();
  return {
    defs,
    get: (tag) => defs.get(tag),
    define(tag, cls) {
      if (defs.has(tag)) throw new Error(`${tag} already defined`);
      defs.set(tag, cls);
      (waiting.get(tag) || []).forEach((resolve) => resolve(cls));
    },
    whenDefined(tag) {
      if (defs.has(tag)) return Promise.resolve(defs.get(tag));
      return new Promise((resolve) => waiting.set(tag, [...(waiting.get(tag) || []), resolve]));
    },
  };
}

const native = registry();
globalThis.window = globalThis;
globalThis.HTMLElement = class {};
globalThis.document = { documentElement: { lang: 'en' }, createElement: () => ({}) };
globalThis.customElements = native;

await import(pathToFileURL(join(tmp, 'ha-microgreens-card.js')).href);

// The polyfill lands, then the app defines <home-assistant> through it (the
// polyfill backs every tag with a native stand-in).
const shim = registry();
globalThis.customElements = shim;
shim.define('home-assistant', class {});
native.define('home-assistant', class {});
await new Promise((resolve) => setTimeout(resolve, 0));

let failed = 0;
for (const tag of ['ha-microgreens-card', 'ha-microgreens-card-editor', 'microgreens-card', 'microgreens-plot-card']) {
  try {
    assert.ok(shim.get(tag), `${tag} missing from the registry in use`);
    assert.equal(native.get(tag), undefined, `${tag} defined in the replaced registry`);
    console.log(`ok   ${tag} defined after the registry swap`);
  } catch (err) {
    failed += 1;
    console.log(`FAIL ${err.message}`);
  }
}
console.log(`${4 - failed}/4 passed`);
process.exit(failed ? 1 : 0);
