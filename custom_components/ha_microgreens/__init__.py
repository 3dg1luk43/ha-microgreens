# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Microgreens: plan, grow and harvest microgreen trays from Home Assistant."""
from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from . import frontend, services, ws_api
from .const import DOMAIN, LEGACY_DOMAIN
from .manager import MicrogreensManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.TODO,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type MicrogreensConfigEntry = ConfigEntry[MicrogreensManager]

ISSUE_LEGACY_ENTRY = "legacy_entry"
KEY_LISTENERS = "listeners"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register what must exist even before (or without) a loaded entry."""
    hass.data.setdefault(DOMAIN, {KEY_LISTENERS: set()})
    ws_api.async_register(hass)
    services.async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MicrogreensConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {KEY_LISTENERS: set()})
    listeners: set[Callable[[], None]] = domain_data[KEY_LISTENERS]
    integration = await async_get_integration(hass, DOMAIN)
    manager = MicrogreensManager(hass, entry, version=str(integration.version or ""), listeners=listeners)
    await manager.async_setup()
    entry.runtime_data = manager
    # The hub exists before any plot device, so plots can name it as their parent.
    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Microgreens",
        manufacturer="Microgreens",
        model="Grow planner",
        entry_type=dr.DeviceEntryType.SERVICE,
        sw_version=manager.version or None,
    )
    manager.hub_device_id = hub.id

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await frontend.async_setup(hass)
    _check_legacy_entry(hass)
    # Panels that subscribed while the entry was not loaded get data now.
    manager._changed(save=False)  # pylint: disable=protected-access
    return True


async def async_unload_entry(hass: HomeAssistant, entry: MicrogreensConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_unload()
        frontend.async_teardown(hass)
    return unloaded


async def _async_options_updated(hass: HomeAssistant, entry: MicrogreensConfigEntry) -> None:
    entry.runtime_data.async_apply_options()


def _check_legacy_entry(hass: HomeAssistant) -> None:
    """Point at a leftover 0.1.x ``microgreens`` entry, which this one replaced."""
    legacy = hass.config_entries.async_entries(LEGACY_DOMAIN)
    if legacy:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_LEGACY_ENTRY,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_LEGACY_ENTRY,
            data={"entry_ids": [e.entry_id for e in legacy]},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_LEGACY_ENTRY)

