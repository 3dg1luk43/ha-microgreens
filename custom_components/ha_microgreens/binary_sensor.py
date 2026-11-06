# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Binary sensors: any tray needs water, and per plot needs water."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MicrogreensConfigEntry
from .entity import MicrogreensEntity, PlotEntity, async_setup_plot_platform
from .manager import MicrogreensManager
from .models import Plot
from . import schedule


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MicrogreensConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    manager = entry.runtime_data
    await async_setup_plot_platform(
        hass,
        manager,
        async_add_entities,
        [WateringDueSensor(manager)],
        lambda m, plot: [NeedsWaterSensor(m, plot)],
    )


class WateringDueSensor(MicrogreensEntity, BinarySensorEntity):
    def __init__(self, manager: MicrogreensManager) -> None:
        super().__init__(manager, "watering_due")

    @property
    def is_on(self) -> bool:
        today = self.manager.today()
        return any(schedule.computed(p, today)["needs_water"] for p in self.manager.data.plantings)


class NeedsWaterSensor(PlotEntity, BinarySensorEntity):
    def __init__(self, manager: MicrogreensManager, plot: Plot) -> None:
        super().__init__(manager, plot, "needs_water")

    @property
    def is_on(self) -> bool:
        planting = self.planting
        return bool(planting and schedule.computed(planting, self.manager.today())["needs_water"])
