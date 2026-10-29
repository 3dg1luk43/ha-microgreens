# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""WebSocket API for the panel and the card.

Reads and the everyday tray actions (water, uncover, harvest, ...) are open to
every user, so a household member can keep the trays going. Changing crops,
plots, settings, history and backups needs an administrator.

A refused write answers with ``code`` = the strings.json ``exceptions`` key
and its placeholders, which the frontend localises itself.
"""
from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_ACTIONS,
    CONF_DIGEST_ENABLED,
    CONF_DIGEST_TIME,
    CONF_NOTIFY_TARGETS,
    CONF_PERSISTENT,
    CONF_REMINDER_ENABLED,
    CONF_REMINDER_TIME,
    DISCARD_REASONS,
    DOMAIN,
)
from .manager import MicrogreensManager, loaded_manager
from .models import MicrogreensError, to_jsonable
from .notification_rules import normalize_options

KEY_LISTENERS = "listeners"
ERR_NOT_LOADED = "not_loaded"

Handler = Callable[[HomeAssistant, websocket_api.ActiveConnection, dict[str, Any], MicrogreensManager], Any]


def _with_manager(func: Handler) -> Callable[..., Any]:
    """Resolve the manager and turn a refused write into a localisable error."""

    @functools.wraps(func)
    def wrapper(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
        manager = loaded_manager(hass)
        if manager is None:
            connection.send_error(msg["id"], ERR_NOT_LOADED, "Microgreens is not loaded")
            return
        try:
            result = func(hass, connection, msg, manager)
        except MicrogreensError as err:
            _send_refusal(connection, msg["id"], err)
            return
        connection.send_result(msg["id"], to_jsonable(result))

    return wrapper


def _with_manager_async(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    async def wrapper(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
        manager = loaded_manager(hass)
        if manager is None:
            connection.send_error(msg["id"], ERR_NOT_LOADED, "Microgreens is not loaded")
            return
        try:
            result = await func(hass, connection, msg, manager)
        except MicrogreensError as err:
            _send_refusal(connection, msg["id"], err)
            return
        connection.send_result(msg["id"], to_jsonable(result))

    return wrapper


def _send_refusal(connection: websocket_api.ActiveConnection, msg_id: int, err: MicrogreensError) -> None:
    connection.send_error(
        msg_id,
        err.key,
        err.key,
        translation_key=err.key,
        translation_domain=DOMAIN,
        translation_placeholders=err.placeholders,
    )


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]) -> None:
    """Push the full snapshot now and after every change.

    The listener is registered on the domain, not on one manager, so a panel
    left open across an entry reload carries on; it asks for the manager each
    time and says ``loaded: false`` while there is none.
    """
    listeners: set[Callable[[], None]] = hass.data[DOMAIN][KEY_LISTENERS]

    @callback
    def forward() -> None:
        manager = loaded_manager(hass)
        payload = {"loaded": False} if manager is None else {"loaded": True, **manager.snapshot()}
        connection.send_message(websocket_api.event_message(msg["id"], payload))

    listeners.add(forward)

    @callback
    def unsubscribe() -> None:
        listeners.discard(forward)

    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
    forward()


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/snapshot"})
@callback
@_with_manager
def ws_snapshot(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    return manager.snapshot()


# --------------------------------------------------------------------------- #
# Everyday actions (any user)
# --------------------------------------------------------------------------- #

_PLANTING = {vol.Required("planting_id"): str}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/planting/sow",
        vol.Required("plot_ids"): vol.All([str], vol.Length(min=1, max=200)),
        vol.Required("profile_id"): str,
        vol.Optional("sown_on"): vol.Any(None, str),
        vol.Optional("label", default=""): str,
        vol.Optional("notes", default=""): str,
    }
)
@callback
@_with_manager
def ws_sow(hass, connection, msg, manager: MicrogreensManager) -> list[str]:
    created = manager.sow(
        msg["plot_ids"], msg["profile_id"], msg.get("sown_on"), label=msg["label"], notes=msg["notes"]
    )
    return [p.id for p in created]


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/planting/update",
        **_PLANTING,
        vol.Required("changes"): {
            vol.Optional("plot_id"): str,
            vol.Optional("sown_on"): str,
            vol.Optional("label"): str,
            vol.Optional("notes"): str,
            vol.Optional("crop_name"): str,
            vol.Optional("soak_hours"): vol.Coerce(float),
            vol.Optional("cover_days"): vol.Coerce(float),
            vol.Optional("light_days"): vol.Coerce(float),
            vol.Optional("harvest_window_days"): vol.Coerce(float),
            vol.Optional("water_every_days"): vol.Coerce(float),
            vol.Optional("uncovered_on"): vol.Any(None, str),
            vol.Optional("last_watered_on"): vol.Any(None, str),
        },
    }
)
@callback
@_with_manager
def ws_update_planting(hass, connection, msg, manager: MicrogreensManager) -> str:
    return manager.update_planting(msg["planting_id"], msg["changes"]).id


_ACTIONS = ("soak", "sow", "uncover", "water", "shift", "harvest", "discard")


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/planting/action",
        **_PLANTING,
        vol.Required("action"): vol.In(_ACTIONS),
        vol.Optional("days"): vol.Coerce(int),
        vol.Optional("yield_grams"): vol.Any(None, vol.Coerce(float)),
        vol.Optional("rating"): vol.Any(None, vol.Coerce(int)),
        vol.Optional("notes", default=""): str,
        vol.Optional("ended_on"): vol.Any(None, str),
        vol.Optional("reason", default=""): vol.Any("", vol.In(DISCARD_REASONS)),
    }
)
@callback
@_with_manager
def ws_planting_action(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    pid = msg["planting_id"]
    action = msg["action"]
    if action == "soak":
        manager.soak(pid)
    elif action == "sow":
        manager.confirm_sown(pid)
    elif action == "uncover":
        manager.uncover(pid)
    elif action == "water":
        manager.water([pid])
    elif action == "shift":
        manager.shift(pid, msg.get("days", 1))
    elif action == "harvest":
        entry = manager.harvest(
            pid,
            yield_grams=msg.get("yield_grams"),
            rating=msg.get("rating"),
            notes=msg["notes"],
            ended_on=msg.get("ended_on"),
        )
        return {"history_id": entry.id}
    elif action == "discard":
        entry = manager.discard(pid, reason=msg["reason"], notes=msg["notes"])
        return {"history_id": entry.id if entry else None}
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/water",
        vol.Optional("planting_ids"): vol.Any(None, [str]),
    }
)
@callback
@_with_manager
def ws_water(hass, connection, msg, manager: MicrogreensManager) -> dict[str, int]:
    return {"watered": manager.water(msg.get("planting_ids"))}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/task/complete", vol.Required("task_id"): str}
)
@callback
@_with_manager
def ws_complete_task(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.complete_task(msg["task_id"])
    return {}


# --------------------------------------------------------------------------- #
# Configuration (administrators)
# --------------------------------------------------------------------------- #


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/profile/save",
        vol.Required("profile"): {
            vol.Optional("id"): vol.Any(None, str),
            vol.Required("name"): str,
            vol.Optional("color"): vol.Any(None, str),
            vol.Optional("soak_hours"): vol.Coerce(float),
            vol.Optional("cover_days"): vol.Coerce(float),
            vol.Optional("light_days"): vol.Coerce(float),
            vol.Optional("harvest_window_days"): vol.Coerce(float),
            vol.Optional("water_every_days"): vol.Coerce(float),
            vol.Optional("seed_grams"): vol.Any(None, vol.Coerce(float)),
            vol.Optional("notes"): str,
        },
    }
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_save_profile(hass, connection, msg, manager: MicrogreensManager) -> dict[str, str]:
    return {"id": manager.save_profile(msg["profile"]).id}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/profile/delete", vol.Required("profile_id"): str}
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_delete_profile(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.delete_profile(msg["profile_id"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/plot/save",
        vol.Required("plot"): {
            vol.Optional("id"): vol.Any(None, str),
            vol.Required("name"): str,
            vol.Optional("location"): str,
        },
    }
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_save_plot(hass, connection, msg, manager: MicrogreensManager) -> dict[str, str]:
    return {"id": manager.save_plot(msg["plot"]).id}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/plot/delete",
        vol.Required("plot_id"): str,
        vol.Optional("force", default=False): bool,
    }
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_delete_plot(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.delete_plot(msg["plot_id"], force=msg["force"])
    return {}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/plot/reorder", vol.Required("plot_ids"): [str]}
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_reorder_plots(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.reorder_plots(msg["plot_ids"])
    return {}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history/update",
        vol.Required("history_id"): str,
        vol.Required("changes"): {
            vol.Optional("yield_grams"): vol.Any(None, vol.Coerce(float)),
            vol.Optional("rating"): vol.Any(None, vol.Coerce(int)),
            vol.Optional("notes"): str,
            vol.Optional("reason"): vol.Any("", vol.In(DISCARD_REASONS)),
            vol.Optional("ended_on"): str,
        },
    }
)
@callback
@_with_manager
def ws_update_history(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    # Not admin-only: recording a yield is part of harvesting.
    manager.update_history(msg["history_id"], msg["changes"])
    return {}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/history/reopen", vol.Required("history_id"): str}
)
@callback
@_with_manager
def ws_reopen_history(hass, connection, msg, manager: MicrogreensManager) -> dict[str, str]:
    # Not admin-only: it is the undo of a harvest, which anyone may do.
    return {"planting_id": manager.reopen_history(msg["history_id"]).id}


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/history/delete", vol.Required("history_id"): str}
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_delete_history(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.delete_history(msg["history_id"])
    return {}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/settings/get"})
@websocket_api.require_admin
@callback
@_with_manager
def ws_get_settings(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    return {"options": dict(manager.options), "targets": available_targets(hass)}


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/settings/save",
        vol.Required("options"): {
            vol.Optional(CONF_NOTIFY_TARGETS): [str],
            vol.Optional(CONF_PERSISTENT): bool,
            vol.Optional(CONF_DIGEST_ENABLED): bool,
            vol.Optional(CONF_DIGEST_TIME): str,
            vol.Optional(CONF_REMINDER_ENABLED): bool,
            vol.Optional(CONF_REMINDER_TIME): str,
            vol.Optional(CONF_ACTIONS): bool,
        },
    }
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_save_settings(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    options = normalize_options({**manager.options, **msg["options"]})
    # The update listener applies them (manager.async_apply_options).
    hass.config_entries.async_update_entry(manager.entry, options=options)
    return {"options": options}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/notify/test"})
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager_async
async def ws_notify_test(hass, connection, msg, manager: MicrogreensManager) -> dict[str, int]:
    return {"sent": await manager.async_send_test()}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/notify/digest"})
@websocket_api.require_admin
@websocket_api.async_response
@_with_manager_async
async def ws_notify_digest(hass, connection, msg, manager: MicrogreensManager) -> dict[str, bool]:
    return {"sent": await manager.async_send_digest(force=True)}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/backup/export"})
@websocket_api.require_admin
@callback
@_with_manager
def ws_export(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    return manager.export()


@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/backup/import", vol.Required("backup"): dict}
)
@websocket_api.require_admin
@callback
@_with_manager
def ws_import(hass, connection, msg, manager: MicrogreensManager) -> dict[str, Any]:
    manager.import_backup(msg["backup"])
    return {}


def available_targets(hass: HomeAssistant) -> list[str]:
    """Notify services (legacy, incl. mobile_app_*) and notify entities."""
    skip = {"send_message", "persistent_notification"}
    services = [f"notify.{name}" for name in hass.services.async_services_for_domain("notify") if name not in skip]
    entities = [state.entity_id for state in hass.states.async_all("notify")]
    return sorted(dict.fromkeys([*services, *entities]))


COMMANDS = (
    ws_subscribe,
    ws_snapshot,
    ws_sow,
    ws_update_planting,
    ws_planting_action,
    ws_water,
    ws_complete_task,
    ws_save_profile,
    ws_delete_profile,
    ws_save_plot,
    ws_delete_plot,
    ws_reorder_plots,
    ws_update_history,
    ws_reopen_history,
    ws_delete_history,
    ws_get_settings,
    ws_save_settings,
    ws_notify_test,
    ws_notify_digest,
    ws_export,
    ws_import,
)


@callback
def async_register(hass: HomeAssistant) -> None:
    for command in COMMANDS:
        websocket_api.async_register_command(hass, command)
