# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Buttons: water every tray that is due, and water one plot."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MicrogreensConfigEntry
from .const import DOMAIN
from .entity import MicrogreensEntity, PlotEntity, async_setup_plot_platform
from .manager import MicrogreensManager
from .models import Plot


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
        [WaterAllButton(manager)],
        lambda m, plot: [WaterPlotButton(m, plot)],
    )


class WaterAllButton(MicrogreensEntity, ButtonEntity):
    def __init__(self, manager: MicrogreensManager) -> None:
        super().__init__(manager, "water_all")

    async def async_press(self) -> None:
        self.manager.water(None)


class WaterPlotButton(PlotEntity, ButtonEntity):
    def __init__(self, manager: MicrogreensManager, plot: Plot) -> None:
        super().__init__(manager, plot, "water")

    async def async_press(self) -> None:
        planting = self.planting
        if planting is None or planting.planned:
            plot = self.manager.data.plot(self.plot_id)
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="plot_empty",
                translation_placeholders={"plot": plot.name if plot else self.plot_id},
            )
        self.manager.water([planting.id])
