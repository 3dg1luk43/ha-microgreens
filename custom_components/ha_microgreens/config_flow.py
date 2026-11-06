# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Config flow (one confirm step) and the notification options.

Everything else (crops, plots, plantings) is edited in the panel. The panel's
Settings tab writes the same options as this flow, through the same
``normalize_options``.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ACTIONS,
    CONF_DIGEST_ENABLED,
    CONF_DIGEST_TIME,
    CONF_NOTIFY_TARGETS,
    CONF_PERSISTENT,
    CONF_REMINDER_ENABLED,
    CONF_REMINDER_TIME,
    CONFIG_ENTRY_VERSION,
    DOMAIN,
    LEGACY_DOMAIN,
)
from .notification_rules import legacy_options, normalize_options
from .ws_api import available_targets


class MicrogreensConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = CONFIG_ENTRY_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        legacy = self.hass.config_entries.async_entries(LEGACY_DOMAIN)
        if user_input is None:
            return self.async_show_form(step_id="user")
        # Carry the 0.1.x notification target and digest time over, if any.
        options = legacy_options(legacy[0].options) if legacy else normalize_options({})
        return self.async_create_entry(title="Microgreens", data={}, options=options)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return MicrogreensOptionsFlow()


class MicrogreensOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=normalize_options(user_input))
        current = normalize_options(self.config_entry.options)
        targets = sorted(dict.fromkeys([*available_targets(self.hass), *current[CONF_NOTIFY_TARGETS]]))
        schema = vol.Schema(
            {
                vol.Optional(CONF_NOTIFY_TARGETS, default=current[CONF_NOTIFY_TARGETS]): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=targets,
                        multiple=True,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(CONF_PERSISTENT, default=current[CONF_PERSISTENT]): selector.BooleanSelector(),
                vol.Required(CONF_DIGEST_ENABLED, default=current[CONF_DIGEST_ENABLED]): selector.BooleanSelector(),
                vol.Required(CONF_DIGEST_TIME, default=current[CONF_DIGEST_TIME]): selector.TimeSelector(),
                vol.Required(CONF_REMINDER_ENABLED, default=current[CONF_REMINDER_ENABLED]): selector.BooleanSelector(),
                vol.Required(CONF_REMINDER_TIME, default=current[CONF_REMINDER_TIME]): selector.TimeSelector(),
                vol.Required(CONF_ACTIONS, default=current[CONF_ACTIONS]): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
