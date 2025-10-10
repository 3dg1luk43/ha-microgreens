
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
* Lovelace dashboards in either mode:
  * Storage mode: resources are auto-registered by the integration.
  * YAML mode: add `/local/ha-microgreens/*.js` resources manually (see below).

---

## Installation

### HACS (Custom Repository)

1. In HACS → Integrations → **Custom repositories**

   * URL: `https://github.com/3dg1luk43/ha-microgreens`
   * Category: **Integration**
2. Install **Microgreens**, then **Restart Home Assistant**.
3. Go to **Settings → Devices & services → “+ Add Integration” → Microgreens**
   Configure options (calendar, notify service, times).

### Lovelace card

* The integration deploys the frontend files to `/config/www/ha-microgreens` and, when Lovelace is in storage mode, auto-registers them as dashboard resources:

  * `/config/www/ha-microgreens/microgreens-card.js`
  * `/config/www/ha-microgreens/microgreens-plot-card.js`

  They are served at `/local/ha-microgreens/*.js`.

If you are using YAML-mode dashboards (or the resources didn’t appear), add them to your configuration manually:

```yaml
lovelace:
  resources:
    - url: /local/ha-microgreens/microgreens-card.js
      type: module
    - url: /local/ha-microgreens/microgreens-plot-card.js
      type: module
  ```

Restart Home Assistant after changing this.


### Using the cards

Cards should be available in card picker, if not, try hard refreshing the dashboard to clear cached javascript. Following is the configuration for manual YAML card.

**Full dashboard**

```yaml
type: custom:microgreens-card
```

**Single plot**

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

### Reinstalling the frontend

Developer Tools → Services → call:

```
service: microgreens.reinstall_frontend
```
This re-copies card files into `/config/www/ha-microgreens/` and (in storage mode) ensures Lovelace resources exist.

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

* Exposes a read-only calendar entity (`calendar.microgreens`).
* Shows one **all-day event** per occupied plot:
  * Start = deployment date, End = `harvest_date + 1`.
  * Summary: `<title_prefix> <Plant Name> @ <Plot ID>`
  * Description includes sticker, plant id, cover/harvest dates, notes.
* Clearing/harvesting a plot removes its calendar event automatically.

No external calendar services are called; events come from the integration’s calendar entity.

---

## Screenshots

Below are example screenshots of the dashboard and editors.

![Single-card dashboard](/img/single-card-dash.png)
Single-card dashboard showing the full microgreens overview card.

![Single plot card](/img/single_plot_card.png)
Compact single-plot card with state, plant, and dates.

![Profile editor](/img/profile-editor.png)
Profiles editor for cover/uncover durations, watering frequency, and notes.

![Plot editor](/img/plot-editor.png)
Plots manager for creating and editing new Plots

---

## Troubleshooting

* **“Custom element doesn’t exist” / “Card type not found”**

  * Restart HA, hard-refresh your browser.
  * Verify `/config/www/ha-microgreens/*.js` exist.
  * If using YAML dashboards, make sure you added `/local/ha-microgreens/*.js` as resources.

* **Buttons do nothing**

  * Ensure the integration is installed and services exist.
  * See **Settings → System → Logs**.

* **Unknown / Entity not found**

  * Integration didn’t create sensors. Ensure one config entry exists. Restart HA.

* **No calendar events**

  * Verify calendar entity supports `create_event`/`delete_event`.

* **No notifications**

  * Ensure `notify.<service>` exists.

---

## Development

* **Backend**: async Python, storage in `.storage/microgreens_store`.
* **Frontend**: plain JS web components, no build step.
* For local testing, serve cards from `/local/ha-microgreens/` with `?v=timestamp` to bust cache:

  ```
  /local/ha-microgreens/microgreens-card.js?v=1234
  ```

---

## Contributing / Issues

* Issues / feature requests: [https://github.com/3dg1luk43/ha-microgreens/issues](https://github.com/3dg1luk43/ha-microgreens/issues)
* PRs welcome. Follow HA coding standards, async safety, and selectors.
* License: MIT
