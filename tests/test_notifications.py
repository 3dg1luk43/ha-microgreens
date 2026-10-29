"""Notifications: content (pure) and delivery through Home Assistant's real
notify schema (conftest.notify_calls)."""
from __future__ import annotations

from datetime import date

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.ha_microgreens.const import PERSISTENT_NOTIFICATION_ID
from custom_components.ha_microgreens.models import Crop, Planting, Plot
from custom_components.ha_microgreens.notification_rules import (
    build_notice,
    fmt,
    legacy_options,
    mobile_data,
    normalize_options,
    parse_time,
)
from custom_components.ha_microgreens.schedule import Task

from .conftest import setup_entry, sow_unwatered

STRINGS = {
    "digest_title": "Microgreens today",
    "reminder_title": "Microgreens: still to do",
    "line_harvest": "Harvest: {items}",
    "line_water": "Water: {items}",
    "line_uncover": "Uncover: {items}",
    "item": "{plot} ({crop})",
    "tag_last_day": "{item}, last day",
    "tag_late": "{item}, late",
    "action_water_all": "Watered all",
    "action_open": "Open",
}
D = date(2026, 10, 29)


def _fixture():
    crop = Crop(name="Radish", color="#e53935")
    plantings = {
        "p1": Planting(id="p1", plot_id="A1", profile_id="r", crop=crop, sown_on=D),
        "p2": Planting(id="p2", plot_id="A2", profile_id="r", crop=crop, sown_on=D),
    }
    plots = {"A1": Plot("A1", "Plot A1"), "A2": Plot("A2", "Plot A2")}
    tasks = [
        Task("harvest", "p1", "A1", D),
        Task("harvest", "p2", "A2", D, last_day=True),
        Task("water", "p1", "A1", D, late=True),
        Task("water", "p2", "A2", D),
    ]
    return tasks, plantings, plots


def test_digest_lists_every_task_grouped() -> None:
    notice = build_notice("digest", *_fixture(), STRINGS)
    assert notice.title == "Microgreens today"
    assert notice.message == (
        "Harvest: Plot A1 (Radish), Plot A2 (Radish), last day\n"
        "Water: Plot A1 (Radish), late, Plot A2 (Radish)"
    )
    assert notice.water_count == 2


def test_reminder_drops_harvests_not_yet_on_their_last_day() -> None:
    notice = build_notice("reminder", *_fixture(), STRINGS)
    assert notice.lines[0] == "Harvest: Plot A2 (Radish), last day"
    tasks, plantings, plots = _fixture()
    assert build_notice("reminder", tasks[:1], plantings, plots, STRINGS) is None
    assert build_notice("digest", [], plantings, plots, STRINGS) is None


def test_fmt_never_raises() -> None:
    assert fmt({"x": "Hello {name"}, "x", name="a") == "Hello {name"
    assert fmt({"x": "{other}"}, "x", name="a") == "{other}"
    assert fmt({}, "missing") == "missing"


def test_mobile_data_actions() -> None:
    notice = build_notice("digest", *_fixture(), STRINGS)
    data = mobile_data(notice, entry_id="E", url="/ha-microgreens", strings=STRINGS, actions=True)
    assert data["tag"] == "ha_microgreens_tasks"
    assert data["actions"][0] == {"action": "HA_MICROGREENS_WATER_ALL_E", "title": "Watered all"}
    assert data["actions"][1] == {"action": "URI", "title": "Open", "uri": "/ha-microgreens"}
    assert "actions" not in mobile_data(notice, entry_id="E", url="/x", strings=STRINGS, actions=False)


def test_options_are_normalized() -> None:
    opts = normalize_options({"notify_targets": ["notify.a", "notify.a", "light.x", " notify.b "], "digest_time": "7:5"})
    assert opts["notify_targets"] == ["notify.a", "notify.b"]
    assert opts["digest_time"] == "08:00:00"  # "7:5" is not HH:MM; default kept
    assert normalize_options({"digest_time": "07:05"})["digest_time"] == "07:05:00"
    assert parse_time("25:00", "09:30") == (9, 30, 0)


def test_legacy_options() -> None:
    opts = legacy_options({"notify_service": "notify.mobile_app_x", "summary_time": "06:45:00", "calendar_entity": "calendar.x"})
    assert opts["notify_targets"] == ["notify.mobile_app_x"]
    assert opts["digest_time"] == "06:45:00"


# --------------------------------------------------------------------------- #
# Delivery in a real Home Assistant
# --------------------------------------------------------------------------- #


async def _entry(hass: HomeAssistant, freezer, **options):
    freezer.move_to("2026-10-29 07:00:00+01:00")
    await hass.config.async_set_time_zone("Europe/Prague")
    return await setup_entry(
        hass,
        {"notify_targets": ["notify.mobile_app_phone", "notify.plain", "notify.gone"], **options},
    )


async def test_digest_at_its_time_once_per_day(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    sow_unwatered(entry.runtime_data, ["A1"], "radish", "2026-10-26")
    freezer.move_to("2026-10-29 08:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert {c.service for c in notify_calls} == {"mobile_app_phone", "plain"}
    mobile = next(c for c in notify_calls if c.service == "mobile_app_phone")
    assert mobile.data["title"] == "Microgreens today"
    assert mobile.data["message"] == "Uncover: Plot A1 (Radish)\nWater: Plot A1 (Radish), late"
    assert mobile.data["data"]["actions"][0]["action"] == f"HA_MICROGREENS_WATER_ALL_{entry.entry_id}"
    plain = next(c for c in notify_calls if c.service == "plain")
    assert "data" not in plain.data  # companion-only keys stay off other targets
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    assert PERSISTENT_NOTIFICATION_ID in notifications
    # A second trigger the same day (e.g. options re-armed the timer) sends nothing.
    notify_calls.clear()
    assert not await entry.runtime_data.async_send_digest()
    assert notify_calls == []


async def test_no_digest_when_nothing_is_due(hass: HomeAssistant, freezer, notify_calls) -> None:
    await _entry(hass, freezer)
    freezer.move_to("2026-10-29 08:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert notify_calls == []


async def test_disabled_digest_stays_quiet(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer, digest_enabled=False)
    sow_unwatered(entry.runtime_data, ["A1"], "radish", "2026-10-26")
    freezer.move_to("2026-10-29 08:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert notify_calls == []


async def test_reminder_only_if_something_is_still_open(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    manager = entry.runtime_data
    (planting,) = sow_unwatered(manager, ["A1"], "radish", "2026-10-26")
    manager.uncover(planting.id)
    manager.water([planting.id])
    freezer.move_to("2026-10-29 19:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert notify_calls == []
    freezer.move_to("2026-10-30 19:00:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # The jump also passed 08:00, so the day's digest went out as well.
    titles = sorted(c.data["title"] for c in notify_calls if c.service == "plain")
    assert titles == ["Microgreens today", "Microgreens: still to do"]


async def test_watering_reminder_does_not_count_as_watering(hass: HomeAssistant, freezer, notify_calls) -> None:
    """0.1.x moved next_watering_due forward when it SENT the reminder, so a
    tray nobody watered was reported watered. Sending must change nothing."""
    entry = await _entry(hass, freezer)
    manager = entry.runtime_data
    (planting,) = sow_unwatered(manager, ["A1"], "radish", "2026-10-27")
    before = planting.last_watered_on
    await manager.async_send_digest(force=True)
    await manager.async_send_reminder(force=True)
    assert planting.last_watered_on == before
    assert any(t.kind == "water" for t in manager.tasks())


async def test_mobile_action_waters_all(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    manager = entry.runtime_data
    sow_unwatered(manager, ["A1", "A2"], "radish", "2026-10-26")
    hass.bus.async_fire("mobile_app_notification_action", {"action": "HA_MICROGREENS_WATER_ALL_other"})
    await hass.async_block_till_done()
    assert any(t.kind == "water" for t in manager.tasks())
    hass.bus.async_fire("mobile_app_notification_action", {"action": f"HA_MICROGREENS_WATER_ALL_{entry.entry_id}"})
    await hass.async_block_till_done()
    assert not any(t.kind == "water" for t in manager.tasks())


async def test_persistent_notification_clears_when_done(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    manager = entry.runtime_data
    (planting,) = sow_unwatered(manager, ["A1"], "radish", "2026-10-26")
    await manager.async_send_digest(force=True)
    notifications = persistent_notification._async_get_or_create_notifications(hass)
    assert "Uncover" in notifications[PERSISTENT_NOTIFICATION_ID]["message"]
    manager.uncover(planting.id)
    await hass.async_block_till_done()
    assert "Uncover" not in notifications[PERSISTENT_NOTIFICATION_ID]["message"]
    manager.water(None)
    await hass.async_block_till_done()
    assert PERSISTENT_NOTIFICATION_ID not in notifications


async def test_options_change_rearms_timers_without_reload(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    manager = entry.runtime_data
    sow_unwatered(manager, ["A1"], "radish", "2026-10-26")
    hass.config_entries.async_update_entry(entry, options={**entry.options, "digest_time": "07:30:00"})
    await hass.async_block_till_done()
    assert entry.runtime_data is manager
    freezer.move_to("2026-10-29 07:30:00+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert notify_calls


async def test_test_notification(hass: HomeAssistant, freezer, notify_calls) -> None:
    entry = await _entry(hass, freezer)
    assert await entry.runtime_data.async_send_test() == 2
    assert all(c.data["message"] == "Test notification from Microgreens." for c in notify_calls)


async def test_notify_entity_target(hass: HomeAssistant, freezer) -> None:
    calls = []

    async def _send(call):
        calls.append(call)

    hass.services.async_register("notify", "send_message", _send)
    hass.states.async_set("notify.kitchen_display", "unknown")
    freezer.move_to("2026-10-29 07:00:00+01:00")
    entry = await setup_entry(hass, {"notify_targets": ["notify.kitchen_display"]})
    sow_unwatered(entry.runtime_data, ["A1"], "radish", "2026-10-26")
    await entry.runtime_data.async_send_digest(force=True)
    assert calls and calls[0].data["entity_id"] == "notify.kitchen_display"


