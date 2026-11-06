# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sensors: today's task count, trays ready, and per plot status/harvest/progress."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import MicrogreensConfigEntry
from .const import PLOT_STATUSES, STATUS_EMPTY, STATUS_OVERDUE, STATUS_READY
from .entity import MicrogreensEntity, PlotEntity, async_setup_plot_platform
from .manager import MicrogreensManager
from .models import Plot
from . import schedule

# Tasks listed in the attribute, so a busy day cannot bloat the state machine.
MAX_TASK_ATTRS = 50


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
        [TasksSensor(manager), ReadySensor(manager)],
        lambda m, plot: [StatusSensor(m, plot), HarvestDateSensor(m, plot), ProgressSensor(m, plot)],
    )


class TasksSensor(MicrogreensEntity, SensorEntity):
    """Open tasks today; the list itself is an attribute."""

    def __init__(self, manager: MicrogreensManager) -> None:
        super().__init__(manager, "tasks_today")

    @property
    def native_value(self) -> int:
        return len(self.manager.tasks())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        tasks = self.manager.tasks()
        return {
            "tasks": [
                {
                    "kind": t.kind,
                    "plot": t.plot_id,
                    "due_on": t.due_on.isoformat(),
                    "late": t.late,
                    "summary": self.manager.task_summary(t),
                }
                for t in tasks[:MAX_TASK_ATTRS]
            ]
        }


class ReadySensor(MicrogreensEntity, SensorEntity):
    """How many plots can be harvested (including late ones)."""

    def __init__(self, manager: MicrogreensManager) -> None:
        super().__init__(manager, "ready_to_harvest")

    def _ready(self) -> list[str]:
        return [
            p.name
            for p in self.manager.plots_sorted()
            if self.manager.plot_status(p.id) in (STATUS_READY, STATUS_OVERDUE)
        ]

    @property
    def native_value(self) -> int:
        return len(self._ready())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"plots": self._ready()}


class StatusSensor(PlotEntity, SensorEntity):
    """The plot's stage: empty, planned, covered, growing, ready, overdue."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = PLOT_STATUSES

    def __init__(self, manager: MicrogreensManager, plot: Plot) -> None:
        super().__init__(manager, plot, "status")

    @property
    def native_value(self) -> str:
        return self.manager.plot_status(self.plot_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        current, nxt = self.manager.current(self.plot_id)
        attrs: dict[str, Any] = {"plot_id": self.plot_id}
        if current is None:
            return attrs
        computed = schedule.computed(current, self.manager.today())
        attrs.update(
            {
                "crop": current.crop.name,
                "label": current.label,
                "sown_on": current.sown_on.isoformat(),
                "uncover_on": computed["uncover_on"],
                "harvest_start": computed["harvest_start"],
                "harvest_end": computed["harvest_end"],
                "day": computed["day"],
                "total_days": computed["total_days"],
                "water_due_on": computed["water_due_on"],
            }
        )
        if nxt is not None:
            attrs["next_crop"] = nxt.crop.name
            attrs["next_sown_on"] = nxt.sown_on.isoformat()
        return attrs


class HarvestDateSensor(PlotEntity, SensorEntity):
    """First day of the current planting's harvest window."""

    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, manager: MicrogreensManager, plot: Plot) -> None:
        super().__init__(manager, plot, "harvest_date")

    @property
    def native_value(self) -> date | None:
        planting = self.planting
        return schedule.times(planting).harvest_start if planting else None


class ProgressSensor(PlotEntity, SensorEntity):
    """How far the current planting is from sowing to its harvest window."""

    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, manager: MicrogreensManager, plot: Plot) -> None:
        super().__init__(manager, plot, "progress")

    @property
    def native_value(self) -> int | None:
        if self.manager.plot_status(self.plot_id) == STATUS_EMPTY:
            return None
        planting = self.planting
        return round(schedule.progress(planting, self.manager.today()) * 100) if planting else None
