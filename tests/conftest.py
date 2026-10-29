"""Shared fixtures. The integration runs inside a real Home Assistant
(pytest-homeassistant-custom-component), so service schemas, the registries,
the WebSocket API and storage are the real ones.

The frontend component is not loaded: its package (home-assistant-frontend)
is not a test dependency, and frontend.py skips itself without it. The panel
and card registration have their own tests that patch the frontend calls.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pytest

# Imported first, so `custom_components` resolves to this repository and not to
# the package Home Assistant's test config ships.
import custom_components.ha_microgreens  # noqa: F401

from homeassistant.components.notify import NOTIFY_SERVICE_SCHEMA
from homeassistant.core import HomeAssistant, ServiceCall
from pytest_homeassistant_custom_component.common import MockConfigEntry

pytest_plugins = ["pytest_homeassistant_custom_component"]

DOMAIN = "ha_microgreens"
TODAY = date(2026, 10, 29)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def notify_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """notify.mobile_app_phone and notify.plain, validated by HA's real schema.

    A MagicMock accepts any payload; this does not, so a payload Home
    Assistant would reject fails here too.
    """
    calls: list[ServiceCall] = []

    async def _record(call: ServiceCall) -> None:
        calls.append(call)

    for name in ("mobile_app_phone", "plain"):
        hass.services.async_register("notify", name, _record, schema=NOTIFY_SERVICE_SCHEMA)
    return calls


async def setup_entry(hass: HomeAssistant, options: dict[str, Any] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Microgreens", data={}, options=options or {}, version=1)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def entry(hass: HomeAssistant, freezer) -> MockConfigEntry:
    freezer.move_to("2026-10-29 10:00:00+01:00")
    await hass.config.async_set_time_zone("Europe/Prague")
    return await setup_entry(hass)


def sow_unwatered(manager, plot_ids, profile_id, sown_on):
    """Sow with a past date and no watering since, so watering is due.

    A real backdated sowing counts as watered today (the tray has been looked
    after); tests that need a thirsty tray say so with this.
    """
    created = manager.sow(plot_ids, profile_id, sown_on)
    for planting in created:
        planting.last_watered_on = planting.sown_on
    return created
