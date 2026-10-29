# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Entity base classes and the per-plot platform wiring."""
from __future__ import annotations

from collections.abc import Callable, Iterable

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, SIGNAL_PLOTS_CHANGED, SIGNAL_UPDATED
from .manager import MicrogreensManager
from .models import Planting, Plot


_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


class MicrogreensEntity(Entity):
    """Pushed by the manager; never polled."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: MicrogreensManager, key: str) -> None:
        self.manager = manager
        entry_id = manager.entry.entry_id
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Microgreens",
            manufacturer="Microgreens",
            model="Grow planner",
            entry_type=DeviceEntryType.SERVICE,
            sw_version=manager.version or None,
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_UPDATED.format(self.manager.entry.entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class PlotEntity(MicrogreensEntity):
    """An entity of one plot, on that plot's device."""

    def __init__(self, manager: MicrogreensManager, plot: Plot, key: str) -> None:
        super().__init__(manager, key)
        entry_id = manager.entry.entry_id
        self.plot_id = plot.id
        self._attr_unique_id = f"{entry_id}_{plot.id}_{key}"
        info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry_id}_{plot.id}")},
            name=plot.name,
            manufacturer="Microgreens",
            model="Plot",
            suggested_area=plot.location or None,
        )
        # HA 2026.8 replaced via_device (identifiers) with via_device_id (registry id).
        if _VIA_DEVICE_ID and manager.hub_device_id:
            info["via_device_id"] = manager.hub_device_id
        else:
            info["via_device"] = (DOMAIN, entry_id)
        self._attr_device_info = info

    @property
    def available(self) -> bool:
        return self.manager.data.plot(self.plot_id) is not None

    @property
    def planting(self) -> Planting | None:
        """The plot's current planting (sown, else its next plan)."""
        return self.manager.current(self.plot_id)[0]

    @callback
    def _handle_update(self) -> None:
        if self.manager.data.plot(self.plot_id) is not None:
            self.async_write_ha_state()


async def async_setup_plot_platform(
    hass: HomeAssistant,
    manager: MicrogreensManager,
    async_add_entities: AddConfigEntryEntitiesCallback,
    hub: Iterable[Entity],
    per_plot: Callable[[MicrogreensManager, Plot], Iterable[Entity]],
) -> None:
    """Add the hub entities, one set per plot, and follow plots being added.

    Deleted plots need nothing here: the manager removes their device, which
    removes their entities.
    """
    created: set[str] = set()

    @callback
    def add_missing() -> None:
        current = {p.id for p in manager.data.plots}
        created.intersection_update(current)
        new = [p for p in manager.plots_sorted() if p.id not in created]
        entities: list[Entity] = []
        for plot in new:
            created.add(plot.id)
            entities.extend(per_plot(manager, plot))
        if entities:
            async_add_entities(entities)

    async_add_entities(list(hub))
    add_missing()
    manager.entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_PLOTS_CHANGED.format(manager.entry.entry_id), add_missing)
    )
