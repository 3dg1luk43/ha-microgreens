# CLAUDE.md

Guidance for Claude Code in this repository. Rules and traps only; the README covers features.
The repo-process model is `/root/ha_washdata` (and `/root/ha_creality_ws`); adapt, don't copy.

## Project

Home Assistant custom integration `ha_microgreens` (0.1.x was `microgreens`): plan, grow and harvest
microgreen trays. Sidebar panel + one Lovelace card (vanilla JS web components, no build step),
WebSocket API, entities per plot, to-do list, notifications. Minimum HA 2026.2.

## Commands

```bash
/root/ha_washdata/.venv/bin/python -m pytest          # whole suite (~30 s): real HA in-process + node tests
/root/ha_washdata/.venv/bin/python -m pytest tests/test_schedule.py -q
TZ=Europe/Prague node tests/js/core.test.mjs          # frontend core unit tests directly
devtools/release_check.sh [--tag v0.2.0]              # release preflight (what CI runs)
cd devtools/testbox && ./up.sh --fresh [--legacy] && python3 hactl.py setup   # real HA container on :8324
python3 devtools/testbox/hactl.py ws ha_microgreens/snapshot
PLAYWRIGHT=/root/ha_washdata/playwright-tests/node_modules/playwright node devtools/screenshots.cjs <out>
```

The washdata venv (HA 2026.2.3, pytest-homeassistant-custom-component) is the local test env; CI installs
`requirements-test.txt`. Use the venv's python for the box scripts too (needs aiohttp).

## Architecture

- `schedule.py` - **single source of truth** for dates, status, occupancy and tasks. Pure; "today" is passed
  in. Entities, notifications, the to-do list and the snapshot all call it; the frontend only renders
  `computed` from the snapshot. Never re-derive a status anywhere else.
- `models.py` - dataclasses, tolerant `from_store`, strict `clean_*` (raise `MicrogreensError(key)`, key =
  strings.json `exceptions` key), `migrate_legacy` (0.1.x store). Pure.
- `notification_rules.py` - options coercion and notification content. Pure; every word comes from
  strings.json `common` (English merged under the user's language).
- `manager.py` - runtime: writes (sync `@callback`s that validate before changing anything, then
  `_changed()`), delayed store save, coalesced push, timers, delivery, mobile action.
- `ws_api.py` / `services.py` - thin adapters over the manager. Config writes need admin; tray actions don't.
- `frontend.py` - static path once per HA run, sidebar panel, card as a frontend **extra module**
  (no Lovelace resource), one-time removal of 0.1.x resources.
- `www/ha-microgreens-core.js` - shared by panel and card: i18n, subscription, renderers, dialogs.

## Rules

- **No em dash (U+2014) anywhere.** Test-enforced. In Python write `chr(0x2014)`; the editor turns escapes into the character.
- **Every user-visible string is translated**: HA-side in `strings.json` (= `translations/en.json`, test-enforced),
  frontend in `www/i18n/en.json` via `I18n.t()` (HTML-escaped) / `tt()` (plain). `tests/test_rules.py` fails on a
  key used in JS but missing, or present but unused (dynamic prefixes are listed there).
- **Non-English translations are produced by a subagent** with the UI context and the existing tone. Never
  machine-translate. Czech needs `_one/_few/_many/_other` plural keys.
- Every service: `services.yaml` + strings.json `services` + `services.SCHEMAS`/`HANDLERS` + `icons.json` (test-enforced).
- Every `MicrogreensError` key exists in strings.json `exceptions` **and** as `error.<key>` in `www/i18n/en.json`.
- `const.py` stays import-free (test execs it standalone).
- "Today" is `manager.today()` (HA time zone). Never `date.today()` / `datetime.now()`.
- A new test must fail with its fix reverted before it counts.
- Do not rename unique_id suffixes, option keys, storage fields or card config keys without a migration.
- Commits conventional and lowercase (`fix: ...`). CHANGELOG: `## X.Y.Z - Unreleased`, TL;DR rewritten as a whole,
  entries as symptom, cause, fix. Version bumps in their own commit.

## Traps

- **Top-level `await` in the panel/card module breaks the panel**: HA creates the element before the module
  finishes, `hass` lands as a plain property and the setter never runs (blank panel). The modules define their
  elements synchronously and `await coreReady` inside `_boot()`; `upgradeProperties()` re-applies early props.
- `DeviceInfo.via_device` is deprecated from HA 2026.8 (removed 2027.8); `entity.py` sends `via_device_id` when
  the running HA has it. The hub device is created in `async_setup_entry` before the platforms for that reason.
- Panel `.mg-*` class names share one shadow root with core's; a reused name silently restyles (the board's
  Today card once collided with the stage-bar `.mg-today` marker). `[hidden]` is forced in core styles because
  `.mg-form{display:flex}` beats the attribute.
- Panel push re-renders the open tab, **except Settings** (it would discard unsaved edits). Dialogs live outside
  the tab container and are never re-rendered.
- WS subscriptions are registered on the domain (`hass.data[DOMAIN]["listeners"]`), not the manager, so an open
  panel survives an entry reload.
- The frontend component is not installed in the test venv; `frontend.py` skips itself without it and
  `tests/test_frontend.py` fakes its three calls. Panel/card rendering is proven only in the box (screenshots).
- Static URL base `/ha_microgreens` (underscore) and panel path `/ha-microgreens` (hyphen) must differ; 0.1.x
  served `/ha-microgreens/` statically, which is why its resources are deleted, not migrated.
- Backdated sowings count as watered today (`sow`); tests that need a thirsty tray use `conftest.sow_unwatered`.

## Release checklist

1. Bump `manifest.json` and add `## X.Y.Z - Unreleased` in a `chore:` commit.
2. On release day date the heading (local date) and run `devtools/release_check.sh --tag vX.Y.Z`.
3. Merge to `main`, tag the merge commit, push only that tag.
