# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Config entry diagnostics: options and the stored data (nothing secret in it)."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import MicrogreensConfigEntry
from .frontend import served_report


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MicrogreensConfigEntry
) -> dict[str, Any]:
    manager = entry.runtime_data
    return {
        "version": manager.version,
        "options": dict(manager.options),
        "today": manager.today().isoformat(),
        "frontend": served_report(hass),
        "data": manager.data.to_store(),
        "tasks": [t.as_dict() for t in manager.tasks()],
    }
