# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Constants. Must stay import-free (tests/test_rules.py execs it standalone)."""

DOMAIN = "ha_microgreens"

CONFIG_ENTRY_VERSION = 1

STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
SAVE_DELAY_S = 1.0

# 0.1.x ran under the domain "microgreens". Its store is read once, on the first
# setup of this domain, and left on disk untouched (models.migrate_legacy).
LEGACY_DOMAIN = "microgreens"
LEGACY_STORAGE_KEY = "microgreens"
LEGACY_STORAGE_VERSION = 1
# URL prefixes 0.1.x put into Lovelace resources; removed once (frontend.py).
LEGACY_RESOURCE_PREFIXES = ("/ha-microgreens/", "/local/ha-microgreens/")

# Frontend
STATIC_URL_BASE = "/ha_microgreens"
PANEL_URL_PATH = "ha-microgreens"
PANEL_ELEMENT = "ha-microgreens-panel"
PANEL_JS = "ha-microgreens-panel.js"
CARD_JS = "ha-microgreens-card.js"
PANEL_ICON = "mdi:sprout"

# ---- options (entry.options) -------------------------------------------------
CONF_NOTIFY_TARGETS = "notify_targets"
CONF_PERSISTENT = "persistent_notification"
CONF_DIGEST_ENABLED = "digest_enabled"
CONF_DIGEST_TIME = "digest_time"
CONF_REMINDER_ENABLED = "reminder_enabled"
CONF_REMINDER_TIME = "reminder_time"
CONF_ACTIONS = "notification_actions"

DEFAULT_OPTIONS = {
    CONF_NOTIFY_TARGETS: [],
    CONF_PERSISTENT: True,
    CONF_DIGEST_ENABLED: True,
    CONF_DIGEST_TIME: "08:00:00",
    CONF_REMINDER_ENABLED: True,
    CONF_REMINDER_TIME: "19:00:00",
    CONF_ACTIONS: True,
}

# ---- planting status ---------------------------------------------------------
STATUS_EMPTY = "empty"
STATUS_PLANNED = "planned"
STATUS_COVERED = "covered"
STATUS_GROWING = "growing"
STATUS_READY = "ready"
STATUS_OVERDUE = "overdue"
PLOT_STATUSES = [
    STATUS_EMPTY,
    STATUS_PLANNED,
    STATUS_COVERED,
    STATUS_GROWING,
    STATUS_READY,
    STATUS_OVERDUE,
]
GROWING_STATUSES = (STATUS_COVERED, STATUS_GROWING, STATUS_READY, STATUS_OVERDUE)

# ---- tasks -------------------------------------------------------------------
TASK_SOAK = "soak"
TASK_SOW = "sow"
TASK_UNCOVER = "uncover"
TASK_WATER = "water"
TASK_HARVEST = "harvest"
# Order tasks are listed in, everywhere (notifications, panel, to-do list).
TASK_ORDER = (TASK_HARVEST, TASK_UNCOVER, TASK_WATER, TASK_SOW, TASK_SOAK)

# ---- history -----------------------------------------------------------------
OUTCOME_HARVESTED = "harvested"
OUTCOME_DISCARDED = "discarded"
DISCARD_REASONS = ("mold", "poor_germination", "pests", "dried_out", "other")

# ---- limits (validated on every write) ---------------------------------------
MAX_PLOTS = 200
MAX_PROFILES = 200
MAX_NAME_LEN = 60
MAX_NOTES_LEN = 1000
MAX_SOAK_HOURS = 72
MAX_STAGE_DAYS = 90
MAX_WINDOW_DAYS = 30
MAX_WATER_DAYS = 30
MAX_YIELD_G = 100000

# A crop's colour when none is chosen, cycled by position. Hex only.
PROFILE_PALETTE = (
    "#43a047",
    "#e53935",
    "#8e24aa",
    "#fb8c00",
    "#1e88e5",
    "#c0ca33",
    "#6d4c41",
    "#00897b",
    "#d81b60",
    "#5e35b1",
)

# Mobile companion action ids. The entry id is appended, so two installs
# (or a stale notification from a removed entry) cannot act on each other.
ACTION_WATER_ALL = "HA_MICROGREENS_WATER_ALL"

PERSISTENT_NOTIFICATION_ID = "ha_microgreens_tasks"

# Dispatcher signal (formatted with the entry id) for "data changed".
SIGNAL_UPDATED = "ha_microgreens_updated_{}"
SIGNAL_PLOTS_CHANGED = "ha_microgreens_plots_changed_{}"

# Seeded on a fresh install only. Names come from strings.json common.crop_<key>.
# (key, soak_hours, cover_days, light_days, harvest_window_days, water_every_days)
DEFAULT_PROFILES = (
    ("arugula", 0, 3, 7, 3, 1),
    ("radish", 0, 3, 5, 3, 1),
    ("broccoli", 0, 3, 7, 3, 1),
    ("mustard", 0, 3, 7, 3, 1),
    ("pea", 12, 4, 8, 3, 1),
    ("sunflower", 12, 4, 6, 2, 1),
    ("coriander", 0, 6, 12, 4, 1),
)
DEFAULT_PLOT_COUNT = 6
