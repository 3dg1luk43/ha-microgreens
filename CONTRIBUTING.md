# Contributing to Microgreens

Thanks for helping. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first.

## Agree the work before you write code

Microgreens is maintained by one volunteer, often with unreleased work in progress, so a surprise pull
request easily duplicates or conflicts with it.

1. **Open an issue** with a template: [Bug report](https://github.com/3dg1luk43/ha-microgreens/issues/new?template=bug_report.yml)
   or [Feature request](https://github.com/3dg1luk43/ha-microgreens/issues/new?template=feature_request.yml).
2. **Say you want to build it** and agree the scope and approach in the issue.
3. **Wait for the maintainer to accept it** (the `accepted` label).
4. **Open the PR**, fill in the template, and link the issue with `Closes #NNN`.

A PR with no agreed issue may be closed. Translations are the exception: they need no issue (see below).

## Bug reports

Include your Microgreens and Home Assistant versions, steps to reproduce, and the error text from the
Home Assistant log (a few full lines are enough). The diagnostics download on the integration page helps
most. For a wrong date or status, say what the tray's crop, sowing date and today's date were.

## Development setup

Python 3.13 and Node 22. Fork [the repository](https://github.com/3dg1luk43/ha-microgreens), then:

```bash
git clone https://github.com/YOUR_USERNAME/ha-microgreens.git
cd ha-microgreens
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements-test.txt
```

Before you push:

```bash
python -m pytest                                          # whole suite: a real Home Assistant in-process + the node tests
ruff check --isolated --select F,E9 custom_components tests devtools
devtools/release_check.sh                                 # what CI runs before a release
```

The panel and card are only proven in a real Home Assistant. With Docker, the test box gives you one on
port 8324:

```bash
cd devtools/testbox && ./up.sh --fresh && python3 hactl.py setup
```

Architecture, rules and known traps: [CLAUDE.md](CLAUDE.md).

## Rules for code changes

- **`schedule.py` is the single source of truth** for dates, status, occupancy and tasks. Entities,
  notifications, the to-do list and the panel read it; never re-derive a status anywhere else.
- **"Today" is `manager.today()`** (Home Assistant's time zone), never `date.today()` or `datetime.now()`.
- **No UI text in code.** Home Assistant strings go in `strings.json` (kept identical to
  `translations/en.json`); panel and card strings go in `www/i18n/en.json` and through `I18n.t()` / `tt()`.
  The tests fail on a missing or unused key.
- **No em dash** (U+2014) anywhere. The tests check it.
- **New services** need `services.yaml`, `strings.json` `services`, `services.SCHEMAS`/`HANDLERS` and
  `icons.json`.
- **No build step.** The panel and card are plain JavaScript modules; edit them directly.
- **Do not rename** unique IDs, option keys, storage fields or card config keys without a migration.
- **Bug fixes come with a test** that fails without the fix.
- **User-facing changes get a CHANGELOG entry** under the unreleased version: symptom, cause, fix.
- One fix or feature per PR. Screenshots for UI changes.

Commits and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/), lowercase:
`fix: keep the harvest date when a tray is uncovered late`.

## Translations

A translation is two files, both copies of the English one with the values translated:

- `custom_components/ha_microgreens/translations/<lang>.json` (Home Assistant: setup, options, entities,
  services, notifications), from `translations/en.json`
- `custom_components/ha_microgreens/www/i18n/<lang>.json` (panel and card), from `www/i18n/en.json`

Rules:

- Keep every `{placeholder}` exactly as it is (the tests compare them with English).
- Plurals use `_one` / `_other` keys, plus the forms your language needs (Czech has `_few` and `_many`).
- Write it as someone who grows microgreens would say it. **No machine translation.**

## License

Contributions are licensed under [AGPL-3.0-or-later](LICENSE), like the project. You keep the copyright
in your own work.
