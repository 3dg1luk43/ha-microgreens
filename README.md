# Microgreens – Home Assistant Integration

**Grow-cycle orchestration for microgreens inside Home Assistant.**  
Tracks plots, plant profiles, deployments, phases (covered / uncovered / mature), watering cadence, daily summaries, and (optionally) calendar events.

> ⚠️ This integration is **designed to be used together** with the Lovelace UI plugin:
> **Microgreens Card** → https://github.com/3dg1luk43/lovelace-microgreens-card  
> Install both for the full experience (management UI, modals, single-plot card).

---

## Features

- **Plant profiles**: cover/uncover durations, watering cadence, notes.
- **Plots**: arbitrary IDs (A1, A2, …), labels, add/remove/rename.
- **Deployments**: schedule a profile on a plot from a start date.
- **Entities**
  - `sensor.microgreens_meta` – current profiles + plots (UI reads this).
  - `sensor.microgreens_plot_<ID>` – per-plot state (`idle`, `covered`, `uncovered`, `mature`) with attributes:
    - `plot_id`, `sticker`, `plant_id`, `plant_name`
    - `days_since_planting`, `cover_end`, `harvest_date`, `next_watering_due`
- **Notifications**
  - Daily summary at configurable time (phase changes + harvests).
  - Watering reminder at configurable time (per watering frequency).
- **Calendar (optional)**
  - If a calendar entity is configured, a **single all-day event spanning start→harvest** is created on deploy (idempotent per plot) and removed on clear.
- **Services** for automations and UI:
  - `microgreens.profile_upsert`, `microgreens.profile_delete`
  - `microgreens.plot_add`, `microgreens.plot_remove`, `microgreens.plot_rename`
  - `microgreens.deploy`, `microgreens.unassign` (clear plot)
  - `microgreens.shift_schedule` (optional utility), `microgreens.seed_defaults`

---

## Requirements

- Home Assistant 2024.6+ (tested on current).
- (Optional) A Calendar integration that supports `calendar.create_event` and `calendar.delete_event`.
- (Recommended) The companion UI plugin:
  - https://github.com/3dg1luk43/lovelace-microgreens-card

---

## Installation (HACS – Custom Repository)

1. **HACS → Integrations →** ⋯ **Custom repositories**
   - URL: `https://github.com/3dg1luk43/ha-microgreens`
   - Category: **Integration**
2. Install **Microgreens**, then **Restart Home Assistant**.
3. **Settings → Devices & services → “+ Add Integration” → Microgreens**  
   This creates one config entry; settings are in the **gear (Options)**.

> Install the **Lovelace plugin** from  
> `https://github.com/3dg1luk43/lovelace-microgreens-card` (HACS → Frontend).

---

## Configuration (Options / Gear icon)

- **Calendar entity**: target calendar (optional). If set and supported, deploy/clear manage a single all-day event per plot.  
- **Notify service**: `notify.<service>` to receive daily summary & watering reminders.
- **Title prefix**: text prefix for calendar summaries (e.g., `[Microgreens]`).
- **Watering time**: HH:MM[:SS] local time for watering reminder.
- **Daily summary time**: HH:MM[:SS] local time for the daily status digest.

> Tips
> - If the notify dropdown is empty, you can type a service manually (e.g., `notify.mobile_app_pixel_7`).
> - Times accept 24-hour `HH:MM` or `HH:MM:SS`.

---

## Default data (first start)

- **Plots**: `A1..A6` with labels “Plot A1”…“Plot A6”.
- **Profiles**:
  - Rukola (`rukola`) – cover 3, uncover 8, water 1
  - Koriandr (`koriandr`) – cover 6, uncover 19, water 1
  - Ředkvička (`redkvicka`) – cover 4, uncover 10, water 1
  - Hrášek (`hrasek`) – cover 5, uncover 16, water 1
  - Hořčice (`horcice`) – cover 3, uncover 11, water 1

---

## Entities

### `sensor.microgreens_meta`
Attributes:
```yaml
profiles:
  - id: rukola
    name: Rukola
    cover_days: 3
    uncover_days: 8
    water: 1
    notes: ""
plots:
  - id: A1
    label: Plot A1
  ...
icon: mdi:database-cog
````

### `sensor.microgreens_plot_<ID>`

State: `idle` | `covered` | `uncovered` | `mature`
Attributes:

```yaml
plot_id: A1
sticker: A1
plant_id: rukola
plant_name: Rukola
days_since_planting: 2
cover_end: 2025-10-01
harvest_date: 2025-10-09
next_watering_due: 2025-09-27
```

---

## Services

> Invoke from Developer Tools → Services (UI or YAML), from automations, or the UI cards.

### `microgreens.profile_upsert`

Create or update a plant profile.

```yaml
service: microgreens.profile_upsert
data:
  id: rukola
  name: Rukola
  cover_days: 3
  uncover_days: 8
  watering_frequency_days: 1
  notes: "Grows fast"
```

### `microgreens.profile_delete`

```yaml
service: microgreens.profile_delete
data: { id: rukola }
```

### `microgreens.plot_add`

```yaml
service: microgreens.plot_add
data: { plot_id: "B1", label: "Tray B1" }
```

### `microgreens.plot_remove`

```yaml
service: microgreens.plot_remove
data: { plot_id: "B1" }
```

### `microgreens.plot_rename`

```yaml
service: microgreens.plot_rename
data: { plot_id: "A1", label: "Plot-3" }
```

### `microgreens.deploy`

Assign a profile to a plot from a date (YYYY-MM-DD).

```yaml
service: microgreens.deploy
data:
  plot_id: A1
  profile_id: rukola
  start_date: "2025-09-26"
  # sticker: "A1"  # optional; defaults to plot id
```

### `microgreens.unassign`

Clear a plot (removes deployment and calendar event).

```yaml
service: microgreens.unassign
data: { plot_id: A1 }
```

### `microgreens.shift_schedule`  *(optional utility)*

Shift all dates for one plot by `days`. Positive → future, negative → past.

```yaml
service: microgreens.shift_schedule
data: { plot_id: A1, days: 1 }
```

### `microgreens.seed_defaults`

Re-apply defaults for missing profiles/plots (idempotent).

```yaml
service: microgreens.seed_defaults
```

---

## Calendar behavior

* One **all-day event** per occupied plot from `start_date` (inclusive) to `harvest_date + 1 day` (exclusive end).
* Summary: `<title_prefix> <Plant Name> @ <Plot ID>`
* Description contains sticker, plant id, cover/harvest dates, notes.
* **Clear** removes the event. If the calendar entity doesn’t exist or the calendar integration doesn’t provide `create_event`/`delete_event`, the integration logs a warning and skips calendar operations.

---

## Storage

* Stored in HA storage (`.storage/microgreens_store`).
* Keys: `plots`, `profiles`, `deployments`.
* Storage schema versioned; integration upgrades handle forward compatibility.

---

## Troubleshooting

* **Gear (Options) shows a 500 / options flow fails**

  * Make sure `config_flow.py` exists and `manifest.json` has `"config_flow": true`.
  * Restart **Home Assistant Core** after updating the integration.
* **Card says “Card type not found” / UI missing**

  * Install the Lovelace plugin: [https://github.com/3dg1luk43/lovelace-microgreens-card](https://github.com/3dg1luk43/lovelace-microgreens-card) and clear frontend cache
* **No calendar events**

  * Ensure the calendar entity in Options exists and supports `calendar.create_event`. Check **Settings → System → Logs** for warnings.
* **No notifications**

  * Verify the selected notify service exists and is spelled `notify.<name>`.
* **Plot sensor shows “idle” but UI claims occupied**

  * Force a state refresh by toggling any option or reloading the page. Sensors recalc at local midnight and on writes.
* **Mobile app shows “Configuration error”**

  * Clear HA app cache, then reopen.

---

## Contributing / Issues

* File issues: [https://github.com/3dg1luk43/ha-microgreens/issues](https://github.com/3dg1luk43/ha-microgreens/issues)
* PRs welcome. Keep code async-safe, avoid blocking I/O, and follow HA selectors for options.
* License: MIT