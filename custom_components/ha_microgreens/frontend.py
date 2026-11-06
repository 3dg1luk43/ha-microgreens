# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Serve the panel and the card, and register them with the frontend.

* ``www/`` is served at ``STATIC_URL_BASE`` once per Home Assistant run (HA has
  no way to unregister a static path). Every URL the frontend loads carries
  ``?v=<build>``, so the long cache headers never serve a stale file.
* The panel is a sidebar entry (``frontend.async_register_built_in_panel``).
* The card is loaded as a frontend extra module on every dashboard, in storage
  and YAML mode alike, so there is no Lovelace resource to manage. The one
  resource job left is deleting what 0.1.x put there (``LEGACY_RESOURCE_PREFIXES``).
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.const import EVENT_COMPONENT_LOADED
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    CARD_JS,
    DOMAIN,
    LEGACY_RESOURCE_PREFIXES,
    PANEL_ELEMENT,
    PANEL_ICON,
    PANEL_JS,
    PANEL_URL_PATH,
    STATIC_URL_BASE,
)

_LOGGER = logging.getLogger(__name__)

WWW = Path(__file__).parent / "www"
KEY_FRONTEND = f"{DOMAIN}_frontend"


def build_version(www: Path = WWW) -> str:
    """A short token that changes with the release and with any asset edit.

    The manifest version alone is not enough: HACS can keep file mtimes from the
    release archive, and a development edit does not bump the version. Blocking
    I/O, run in an executor.
    """
    manifest = Path(__file__).parent / "manifest.json"
    try:
        version = json.loads(manifest.read_text(encoding="utf-8")).get("version", "")
    except (OSError, ValueError):
        version = ""
    digest = hashlib.sha256(version.encode())
    for path in sorted(www.rglob("*")):
        if path.is_file() and path.suffix in (".js", ".json"):
            digest.update(path.relative_to(www).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


async def async_setup(hass: HomeAssistant) -> None:
    """Register static files, the panel and the card. Safe to call again."""
    state: dict[str, Any] = hass.data.setdefault(KEY_FRONTEND, {})
    if "frontend" not in hass.config.components:
        _LOGGER.debug("Frontend not loaded; the panel and card are not registered")
        return
    from homeassistant.components import frontend  # pylint: disable=import-outside-toplevel

    if not state.get("static"):
        await hass.http.async_register_static_paths([StaticPathConfig(STATIC_URL_BASE, str(WWW), True)])
        state["static"] = True

    version = await hass.async_add_executor_job(build_version)
    state["version"] = version

    if not state.get("panel"):
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title="Microgreens",
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL_PATH,
            # ha-panel-custom reads only _panel_custom.
            config={
                "_panel_custom": {
                    "name": PANEL_ELEMENT,
                    "module_url": f"{STATIC_URL_BASE}/{PANEL_JS}?v={version}",
                    "embed_iframe": False,
                    "trust_external": False,
                }
            },
            require_admin=False,
        )
        state["panel"] = True

    card_url = f"{STATIC_URL_BASE}/{CARD_JS}?v={version}"
    if state.get("card") != card_url:
        if state.get("card"):
            frontend.remove_extra_js_url(hass, state["card"])
        frontend.add_extra_js_url(hass, card_url)
        state["card"] = card_url

    _async_cleanup_legacy_resources(hass)


@callback
def async_teardown(hass: HomeAssistant) -> None:
    """Entry unloaded: remove the sidebar entry and the card module."""
    state: dict[str, Any] = hass.data.get(KEY_FRONTEND, {})
    if "frontend" not in hass.config.components:
        return
    from homeassistant.components import frontend  # pylint: disable=import-outside-toplevel

    if state.pop("panel", False):
        frontend.async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
    if card := state.pop("card", None):
        try:
            frontend.remove_extra_js_url(hass, card)
        except KeyError:
            pass


def served_report(hass: HomeAssistant) -> dict[str, Any]:
    state = hass.data.get(KEY_FRONTEND, {})
    return {
        "version": state.get("version"),
        "panel": bool(state.get("panel")),
        "card": state.get("card"),
        "legacy_resources_removed": state.get("legacy_removed", 0),
    }


@callback
def _async_cleanup_legacy_resources(hass: HomeAssistant) -> None:
    """Delete 0.1.x Lovelace resources (they point at files that are gone).

    Storage-mode resources only; YAML-mode ones are the user's file. Waits for
    Lovelace when it is not loaded yet.
    """
    state: dict[str, Any] = hass.data[KEY_FRONTEND]
    if state.get("legacy_checked"):
        return
    if "lovelace" not in hass.config.components:
        if not state.get("legacy_waiting"):
            state["legacy_waiting"] = True

            @callback
            def _loaded(event: Event) -> None:
                if event.data.get("component") == "lovelace":
                    unsub()
                    state["legacy_waiting"] = False
                    _async_cleanup_legacy_resources(hass)

            unsub = hass.bus.async_listen(EVENT_COMPONENT_LOADED, _loaded)
        return
    state["legacy_checked"] = True
    hass.async_create_background_task(_async_remove_legacy(hass), f"{DOMAIN}_legacy_resources")


async def _async_remove_legacy(hass: HomeAssistant) -> None:
    try:
        from homeassistant.components.lovelace.resources import (  # pylint: disable=import-outside-toplevel
            ResourceStorageCollection,
        )
    except ImportError:
        return
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if not isinstance(resources, ResourceStorageCollection):
        return
    try:
        await resources.async_get_info()
        removed = 0
        for item in list(resources.async_items()):
            url = str(item.get("url") or "")
            if url.startswith(LEGACY_RESOURCE_PREFIXES) and "microgreens" in url:
                await resources.async_delete_item(item["id"])
                removed += 1
        hass.data[KEY_FRONTEND]["legacy_removed"] = removed
        if removed:
            _LOGGER.info("Removed %d Lovelace resources left by Microgreens 0.1", removed)
    except Exception:  # pylint: disable=broad-except
        _LOGGER.warning("Could not clean up Microgreens 0.1 Lovelace resources", exc_info=True)
