# Translation PR

Thank you for translating Microgreens! Translation PRs need no accepted issue.

A language has two files, both keyed like the English ones:

- `custom_components/ha_microgreens/translations/<lang>.json`: setup, options, entities, services, notifications (English: `translations/en.json`)
- `custom_components/ha_microgreens/www/i18n/<lang>.json`: the panel and the card (English: `www/i18n/en.json`)

## Checklist

- [ ] I am a native or fluent speaker of the language, or a native speaker reviewed the translation. No machine translation.
- [ ] I have only changed files under `translations/` and `www/i18n/` (no English text, no code).
- [ ] Every `{placeholder}` is kept exactly as in English.
- [ ] Plural keys follow my language's plural forms (English has `_one`/`_other`; Czech, for example, needs `_one`/`_few`/`_many`/`_other`).
- [ ] No em dash (U+2014); use ` - ` instead.
- [ ] `python -m pytest tests/test_rules.py` passes, or I could not run it.
- [ ] I have loaded the translation in Home Assistant and checked the panel, the card and a notification.

## Language

<!-- e.g. German (de), Brazilian Portuguese (pt-BR) -->

## Description

<!-- What you added or corrected. -->

## What was changed

- [ ] New language added
- [ ] Corrected existing translation(s)
- [ ] Updated strings to match recent English changes

## Type of Change

- [x] Translation

## Specific corrections (if applicable)

| Key | Old text | New text | Reason |
|-----|----------|----------|--------|
|     |          |          |        |

## Additional notes

<!-- Regional variants, formal/informal register, terms you were unsure of. -->
