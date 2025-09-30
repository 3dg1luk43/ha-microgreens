# Microgreens – Home Assistant Integration + Lovelace Cards

**Grow-cycle orchestration for microgreens inside Home Assistant, with a full Lovelace UI.**
This repository combines both the backend integration and the frontend cards:

* **Integration** – entities, services, notifications, calendar integration.
* **Cards** – `microgreens-card` (full dashboard) and `microgreens-plot-card` (single plot).

---

## Features

### Integration

* **Plant profiles**
  Define cover/uncover durations, watering cadence, and notes.
* **Plots**
  Arbitrary IDs (A1, A2, …), labels, add/remove/rename.
* **Deployments**
  Schedule a profile on a plot from a start date.
* **Entities**

  * `sensor.microgreens_meta` – current profiles + plots (UI reads this).
  * `sensor.microgreens_plot_<ID>` – per-plot state (`idle`, `covered`, `uncovered`, `mature`) with attributes:

    * `plot_id`, `sticker`, `plant_id`, `plant_name`
    * `days_since_planting`, `cover_end`, `harvest_date`, `next_watering_due`
* **Notifications**

  * Daily summary at configurable time.
  * Watering reminder at configurable time.
* **Calendar (optional)**

  * If configured, one all-day event per deployment (start → harvest).
* **Services**

  * `microgreens.profile_upsert`, `microgreens.profile_delete`
  * `microgreens.plot_add`, `microgreens.plot_remove`, `microgreens.plot_rename`
  * `microgreens.deploy`, `microgreens.unassign`
  * Utilities: `microgreens.shift_schedule`, `microgreens.seed_defaults`

### Cards

* **`microgreens-card`** – full dashboard:

  * Deploy modal (idle plot + profile + start date).
  * Profiles modal (add/edit/delete with validation, ✓ flash on save).
  * Plots modal (add/rename/delete, ✓ flash on save).
  * Responsive grid of plot tiles showing state, plant, dates, with a **Clear** button (confirmation + ✓ animation).
* **`microgreens-plot-card`** – compact card for a single plot:

  * Displays state, plant, uncover/harvest dates.
  * Properties:

    * `plot_id` (required) – e.g. `A1`
    * `title` (optional) – override title
    * `compact` (optional, boolean)

---

## Requirements

* Home Assistant 2024.6+ (tested).
* Optional: Calendar integration with `calendar.create_event` / `calendar.delete_event`.
* No separate card installation needed: cards ship with the integration and auto-load.

---

## Installation (HACS – Custom Repository)

1. **HACS → Integrations →** **Custom repositories**

   * URL: `https://github.com/3dg1luk43/ha-microgreens`
   * Category: **Integration**
2. Install **Microgreens**, then **Restart Home Assistant**.
3. **Settings → Devices & services → “+ Add Integration” → Microgreens**
   Configure options (calendar, notify service, times).
4. The Lovelace cards are installed automatically.
   Add them to your dashboards:

   ```yaml
   type: custom:microgreens-card
   ```

   or

   ```yaml
   type: custom:microgreens-plot-card
   plot_id: A1
   ```

No manual resource configuration is required on current HA versions.
On older HA cores without `add_extra_module_url`, the integration falls back to copying to `/local/microgreens/`.

---

## Configuration (Options)

* **Calendar entity** – optional, adds start→harvest events per plot.
* **Notify service** – e.g. `notify.mobile_app_pixel_7`.
* **Title prefix** – prepended to calendar event summaries.
* **Watering time** – time of daily watering reminder.
* **Daily summary time** – time of daily digest notification.

**Tips**

* If the notify dropdown is empty, type the service manually (`notify.mobile_app_*`).
* Times accept `HH:MM` or `HH:MM:SS`.

---

## Default data (first start)

* **Plots**: `A1..A6` with labels “Plot A1”…“Plot A6”.
* **Profiles**:

  * Arugula – cover 3, uncover 8, water 1
  * Coriander – cover 6, uncover 19, water 1
  * Radish – cover 4, uncover 10, water 1
  * Pea – cover 5, uncover 16, water 1
  * Mustard – cover 3, uncover 11, water 1

---

## Entities

### `sensor.microgreens_meta`

Example attributes:

```yaml
profiles:
  - id: arugula
    name: Arugula
    cover_days: 3
    uncover_days: 8
    water: 1
    notes: ""
plots:
  - id: A1
    label: Plot A1
icon: mdi:database-cog
```

### `sensor.microgreens_plot_<ID>`

Example:

```yaml
state: covered
plot_id: A1
sticker: A1
plant_id: arugula
plant_name: Arugula
days_since_planting: 2
cover_end: 2025-10-01
harvest_date: 2025-10-09
next_watering_due: 2025-09-27
```

---

## Services

Invoke from Developer Tools → Services, automations, or cards.

### `microgreens.profile_upsert`

Create or update a plant profile.

```yaml
service: microgreens.profile_upsert
data:
  id: arugula
  name: Arugula
  cover_days: 3
  uncover_days: 8
  watering_frequency_days: 1
  notes: "Grows fast"
```

### `microgreens.profile_delete`

```yaml
service: microgreens.profile_delete
data:
  id: arugula
```

### `microgreens.plot_add`

```yaml
service: microgreens.plot_add
data:
  plot_id: B1
  label: Tray B1
```

### `microgreens.plot_remove`

```yaml
service: microgreens.plot_remove
data:
  plot_id: B1
```

### `microgreens.plot_rename`

```yaml
service: microgreens.plot_rename
data:
  plot_id: A1
  label: Plot-3
```

### `microgreens.deploy`

Deploy a profile to a plot.

```yaml
service: microgreens.deploy
data:
  plot_id: A1
  profile_id: arugula
  start_date: "2025-09-26"
  # sticker: "A1"  # optional, defaults to plot id
```

### `microgreens.unassign`

Clear a plot.

```yaml
service: microgreens.unassign
data:
  plot_id: A1
```

### `microgreens.shift_schedule`

Shift all dates for one plot.

```yaml
service: microgreens.shift_schedule
data:
  plot_id: A1
  days: 1
```

### `microgreens.seed_defaults`

Re-apply default plots/profiles.

```yaml
service: microgreens.seed_defaults
```

---

## Calendar Behavior

* One **all-day event** per occupied plot.
  Start = deployment date, End = `harvest_date + 1`.
* Summary: `<title_prefix> <Plant Name> @ <Plot ID>`
* Description contains sticker, plant id, cover/harvest dates, notes.
* **Clear** removes the event.
* If the calendar doesn’t support `create_event`/`delete_event`, integration logs a warning and skips.

---

## Cards Usage

### 1) Full dashboard

```yaml
type: custom:microgreens-card
```

### 2) Single plot

```yaml
type: custom:microgreens-plot-card
plot_id: A1
title: Plot-3
compact: true
```

**How they work:**

* Read `sensor.microgreens_meta` for plots/profiles.
* Read `sensor.microgreens_plot_<ID>` for per-plot state.
* Call integration services (`deploy`, `unassign`, etc.).
* Integration remains the single source of truth.

---

## Troubleshooting

* **“Custom element doesn’t exist” / “Card type not found”**

  * Restart HA, clear frontend cache.
  * On old HA versions: add resources manually under **Settings → Dashboards → Resources**:

    * `/local/microgreens/microgreens-card.js`
    * `/local/microgreens/microgreens-plot-card.js`

* **Buttons do nothing**

  * Check integration is installed and services exist.
  * See **Settings → System → Logs**.

* **Unknown / Entity not found**

  * Integration didn’t create sensors. Ensure one config entry exists. Restart HA.

* **No calendar events**

  * Verify calendar entity supports `create_event`/`delete_event`.

* **No notifications**

  * Ensure `notify.<service>` exists.

* **Edits in modals revert while typing**

  * Latest version fixes race conditions; update if needed.

---

## Development

* **Backend**: async Python, storage in `.storage/microgreens_store` (keys: `plots`, `profiles`, `deployments`).
* **Frontend**: plain JS web components, no build step.
* For local testing, serve cards from `/local/` with `?v=timestamp` to bust cache:

  * `/local/microgreens-card.js?v=1234`

---

## Contributing / Issues

* Issues / feature requests: [https://github.com/3dg1luk43/ha-microgreens/issues](https://github.com/3dg1luk43/ha-microgreens/issues)
* PRs welcome. Follow HA coding standards, async safety, and selectors.
* License: MIT
