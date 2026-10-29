# Changelog

## 0.2.0 - Unreleased

A rebuild. The integration is now `ha_microgreens`; 0.1.x data is imported on first setup.

### TL;DR

- Sidebar panel: board, timeline, crops, plots, history, settings.
- One Lovelace card with a visual editor (board, tasks, timeline, one plot).
- Morning digest and evening reminder, phone action buttons, sidebar notification.
- Today's tasks as a to-do list; checking one off does it.
- Harvest log with yield, rating and per-crop statistics; undo.
- No calendar entity any more; the timeline replaces it.

### Breaking

- Domain renamed `microgreens` -> `ha_microgreens` (folder `custom_components/ha_microgreens`). Add the integration again; plots, crops and trays are imported from `.storage/microgreens`, which is left untouched. A repair removes the old entry. Uninstall the old download.
- Entities, services and card names changed; see the README. `custom:microgreens-card` and `custom:microgreens-plot-card` still render (board and plot views).
- Calendar entity, `sensor.microgreens_meta` and the profile/plot services are gone (the panel and its WebSocket API replace them).

### Added

- Stage model with blackout, light and a harvest window; planned sowings with soak and sow reminders; uncovering recorded; succession planning with overlap checks.
- Per plot: status, harvest date and progress sensors, needs-water binary sensor, watered button. Hub: tasks today, ready to harvest, watering due, water all, to-do list.
- Services `sow`, `water`, `uncover`, `harvest`, `discard`, `shift`, `send_digest`, `get_tasks` (by plot ID or plot device).
- Notifications to several targets (notify services or notify entities), with "Watered all" on companion apps.
- Backup export and import, diagnostics, English and Czech.

### Fixed

- Watering reminder marked trays watered when it was sent, not when they were watered. Now only a user action does.
- "Today" came from the host clock (`date.today()`), not Home Assistant's time zone.
- Integration folder did not match its domain (hassfest failure); `water_ack` was documented but never registered; `shift_schedule` was registered twice.
- Card JS was served through a tangle of Lovelace resource migrations; the card now loads as a frontend module with no resource to manage, and the 0.1.x resources are removed.
