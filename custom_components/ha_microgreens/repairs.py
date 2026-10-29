# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Repairs: remove the 0.1.x ``microgreens`` entry this integration replaced."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant

from .const import LEGACY_DOMAIN


class LegacyEntryRepairFlow(ConfirmRepairFlow):
    """Confirm, then delete the old entries. Their data was imported at setup."""

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        if user_input is not None:
            for entry in self.hass.config_entries.async_entries(LEGACY_DOMAIN):
                await self.hass.config_entries.async_remove(entry.entry_id)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    return LegacyEntryRepairFlow()
