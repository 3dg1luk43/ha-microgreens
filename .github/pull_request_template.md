> [!CAUTION]
> **Do not open this PR unless your linked issue already carries the `accepted` label.**
>
> Microgreens does not accept unsolicited code. Open an
> [issue](https://github.com/3dg1luk43/ha-microgreens/issues/new/choose) first, tick "I plan to submit a
> PR", and wait for the `accepted` label so scope is agreed before you write anything.
>
> Closed automatically: PRs linking no issue (after 3 days) and PRs with this template deleted (at
> once) or unfilled (after 5 days). A PR linked to an issue that is not yet accepted waits for the
> maintainer. **Translation PRs** (only `translations/`, `www/i18n/` and `strings.json`) are exempt
> from the accepted-issue requirement and use the translation template instead (see
> [Translations](https://github.com/3dg1luk43/ha-microgreens/blob/main/CONTRIBUTING.md#translations)).

Closes #<!-- must already have the `accepted` label -->

## Description

<!-- What problem does this solve, and how? -->

## Type of Change

- [ ] Bug fix
- [ ] Feature
- [ ] Refactor
- [ ] Docs
- [ ] Tests
- [ ] UI
- [ ] Translation

## Testing

<!-- How did you verify this? For a bug fix, include the Home Assistant and Microgreens versions. -->

- [ ] `python -m pytest` passes (see CONTRIBUTING.md for the test environment)
- [ ] Tests added or updated, and the new test fails with the fix reverted
- [ ] Checked in a real Home Assistant (panel/card changes: screenshot below)

## Checklist

- [ ] The linked issue already had the `accepted` label (or this is a translation PR)
- [ ] No hardcoded user-visible text: `strings.json` (copied to `translations/en.json`) and `www/i18n/en.json`
- [ ] No storage field, option key, unique ID or card config key renamed without a migration
- [ ] README and CHANGELOG updated if the change is user-visible
- [ ] Breaking change? Describe it and the migration path here:

## Notes for reviewers

<!-- Anything else worth knowing. Screenshots welcome for UI changes. -->
