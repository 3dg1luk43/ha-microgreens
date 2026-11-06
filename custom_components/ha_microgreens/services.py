# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Service actions, for automations and scripts.

A tray is addressed by ``plot`` (its id, e.g. ``A1``) or ``device_id`` (the
plot's device). Each action works on that plot's current planting.
Every service is listed in services.yaml and strings.json; tests/test_rules.py
keeps the three in step.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import DISCARD_REASONS, DOMAIN, MAX_STAGE_DAYS
from .manager import MicrogreensManager, loaded_manager
from .models import MicrogreensError, Planting

ATTR_PLOT = "plot"
ATTR_DEVICE = "device_id"

_TARGET = {
    vol.Optional(ATTR_PLOT): cv.string,
    vol.Optional(ATTR_DEVICE): cv.string,
}

SCHEMAS: dict[str, vol.Schema] = {
    "sow": vol.Schema(
        {
            **_TARGET,
            vol.Optional("crop"): cv.string,
            vol.Optional("date"): cv.date,
            vol.Optional("label", default=""): cv.string,
            vol.Optional("notes", default=""): cv.string,
        }
    ),
    "water": vol.Schema(_TARGET),
    "uncover": vol.Schema(_TARGET),
    "harvest": vol.Schema(
        {
            **_TARGET,
            vol.Optional("yield_grams"): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional("rating"): vol.All(vol.Coerce(int), vol.Range(min=1, max=5)),
            vol.Optional("notes", default=""): cv.string,
        }
    ),
    "discard": vol.Schema(
        {
            **_TARGET,
            vol.Optional("reason", default="other"): vol.In(DISCARD_REASONS),
            vol.Optional("notes", default=""): cv.string,
        }
    ),
    "shift": vol.Schema(
        {
            **_TARGET,
            vol.Required("days"): vol.All(vol.Coerce(int), vol.Range(min=-MAX_STAGE_DAYS, max=MAX_STAGE_DAYS)),
        }
    ),
    "send_digest": vol.Schema({}),
    "get_tasks": vol.Schema({}),
}


def _resolve_manager(hass: HomeAssistant) -> MicrogreensManager:
    manager = loaded_manager(hass)
    if manager is None:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return manager


def _plot_id(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> str:
    if call.data.get(ATTR_DEVICE):
        device = dr.async_get(hass).async_get(call.data[ATTR_DEVICE])
        prefix = f"{manager.entry.entry_id}_"
        ident = next(
            (i[1] for i in (device.identifiers if device else ()) if i[0] == DOMAIN and i[1].startswith(prefix)),
            None,
        )
        if ident is None:
            raise MicrogreensError("not_a_plot_device")
        return ident[len(prefix) :]
    if call.data.get(ATTR_PLOT):
        wanted = str(call.data[ATTR_PLOT]).strip()
        for plot in manager.data.plots:
            if wanted in (plot.id, plot.name) or wanted.lower() == plot.id.lower():
                return plot.id
        raise MicrogreensError("unknown_plot", plot=wanted)
    raise MicrogreensError("no_plot")


def _current(manager: MicrogreensManager, plot_id: str, *, sown: bool = True) -> Planting:
    current, _ = manager.current(plot_id)
    if current is None or (sown and current.planned):
        raise MicrogreensError("plot_empty", plot=manager.data.plot(plot_id).name)
    return current


async def _sow(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    plot_id = _plot_id(hass, manager, call)
    if call.data.get("crop"):
        crop = str(call.data["crop"]).strip()
        profile = next((p for p in manager.data.profiles if crop in (p.id, p.name)), None)
        manager.sow(
            [plot_id],
            profile.id if profile else crop,
            call.data.get("date"),
            label=call.data["label"],
            notes=call.data["notes"],
        )
        return
    # No crop: confirm the plot's plan (its seeds went in today).
    current, _ = manager.current(plot_id)
    if current is None or not current.planned:
        raise MicrogreensError("no_plan", plot=manager.data.plot(plot_id).name)
    manager.confirm_sown(current.id)


async def _water(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    if not call.data.get(ATTR_PLOT) and not call.data.get(ATTR_DEVICE):
        manager.water(None)
        return
    manager.water([_current(manager, _plot_id(hass, manager, call)).id])


async def _uncover(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    manager.uncover(_current(manager, _plot_id(hass, manager, call)).id)


async def _harvest(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    manager.harvest(
        _current(manager, _plot_id(hass, manager, call)).id,
        yield_grams=call.data.get("yield_grams"),
        rating=call.data.get("rating"),
        notes=call.data["notes"],
    )


async def _discard(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    manager.discard(
        _current(manager, _plot_id(hass, manager, call), sown=False).id,
        reason=call.data["reason"],
        notes=call.data["notes"],
    )


async def _shift(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    manager.shift(_current(manager, _plot_id(hass, manager, call), sown=False).id, call.data["days"])


async def _send_digest(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> None:
    await manager.async_send_digest(force=True)


async def _get_tasks(hass: HomeAssistant, manager: MicrogreensManager, call: ServiceCall) -> ServiceResponse:
    plots = {p.id: p for p in manager.data.plots}
    out = []
    for task in manager.tasks():
        planting = manager.data.planting(task.planting_id)
        out.append(
            {
                **task.as_dict(),
                "plot": plots[task.plot_id].name if task.plot_id in plots else task.plot_id,
                "crop": planting.crop.name if planting else None,
                "summary": manager.task_summary(task),
            }
        )
    return {"date": manager.today().isoformat(), "tasks": out}


HANDLERS: dict[str, Callable[[HomeAssistant, MicrogreensManager, ServiceCall], Awaitable[Any]]] = {
    "sow": _sow,
    "water": _water,
    "uncover": _uncover,
    "harvest": _harvest,
    "discard": _discard,
    "shift": _shift,
    "send_digest": _send_digest,
    "get_tasks": _get_tasks,
}


def _wrap(hass: HomeAssistant, name: str) -> Callable[[ServiceCall], Awaitable[Any]]:
    handler = HANDLERS[name]

    async def service(call: ServiceCall) -> Any:
        manager = _resolve_manager(hass)
        try:
            return await handler(hass, manager, call)
        except MicrogreensError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key=err.key,
                translation_placeholders=err.placeholders,
            ) from err

    return service


@callback
def async_register(hass: HomeAssistant) -> None:
    for name in HANDLERS:
        hass.services.async_register(
            DOMAIN,
            name,
            _wrap(hass, name),
            schema=SCHEMAS[name],
            supports_response=SupportsResponse.ONLY if name == "get_tasks" else SupportsResponse.NONE,
        )
