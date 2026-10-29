"""The integration in a real Home Assistant: setup, entities, services, to-do."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from homeassistant.components.todo import DOMAIN as TODO_DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import DOMAIN, setup_entry, sow_unwatered

TODAY = date(2026, 10, 29)


async def test_fresh_install_seeds_plots_and_crops(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    assert [p.id for p in manager.data.plots] == ["A1", "A2", "A3", "A4", "A5", "A6"]
    assert manager.data.plots[0].name == "Plot A1"
    assert manager.data.profile("radish").name == "Radish"
    assert hass.states.get("sensor.plot_a1_status").state == "empty"
    assert hass.states.get("sensor.microgreens_tasks_today").state == "0"
    assert hass.states.get("binary_sensor.microgreens_watering_due").state == "off"
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert len(devices) == 7  # hub + six plots


async def test_sow_water_uncover_harvest_through_services(hass: HomeAssistant, entry, freezer) -> None:
    await hass.services.async_call(DOMAIN, "sow", {"plot": "A1", "crop": "radish"}, blocking=True)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.plot_a1_status")
    assert state.state == "covered"
    assert state.attributes["crop"] == "Radish"
    assert state.attributes["harvest_start"] == "2026-11-06"
    assert hass.states.get("sensor.plot_a1_harvest_date").state == "2026-11-06"
    assert hass.states.get("sensor.plot_a1_progress").state == "0"

    freezer.tick(timedelta(days=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.plot_a1_needs_water").state == "on"
    await hass.services.async_call(DOMAIN, "water", {"plot": "a1"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.plot_a1_needs_water").state == "off"

    await hass.services.async_call(DOMAIN, "uncover", {"plot": "Plot A1"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.plot_a1_status").state == "growing"

    await hass.services.async_call(
        DOMAIN, "harvest", {"plot": "A1", "yield_grams": 210.5, "rating": 4}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.plot_a1_status").state == "empty"
    history = entry.runtime_data.data.history
    assert len(history) == 1
    assert (history[0].outcome, history[0].yield_grams, history[0].rating) == ("harvested", 210.5, 4)


async def test_service_errors_are_translated(hass: HomeAssistant, entry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "uncover", {"plot": "A1"}, blocking=True)
    assert err.value.translation_key == "plot_empty"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "sow", {"plot": "Q9", "crop": "radish"}, blocking=True)
    assert err.value.translation_key == "unknown_plot"
    await hass.services.async_call(DOMAIN, "sow", {"plot": "A1", "crop": "radish"}, blocking=True)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "sow", {"plot": "A1", "crop": "pea"}, blocking=True)
    assert err.value.translation_key == "plot_busy"
    assert err.value.translation_placeholders["crop"] == "Radish"


async def test_service_by_device(hass: HomeAssistant, entry) -> None:
    device = dr.async_get(hass).async_get_device({(DOMAIN, f"{entry.entry_id}_A2")})
    await hass.services.async_call(DOMAIN, "sow", {"device_id": device.id, "crop": "pea"}, blocking=True)
    current, _ = entry.runtime_data.current("A2")
    assert current.crop.name == "Pea shoots"
    hub = dr.async_get(hass).async_get_device({(DOMAIN, entry.entry_id)})
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "water", {"device_id": hub.id}, blocking=True)
    assert err.value.translation_key == "not_a_plot_device"


async def test_planned_sowing_then_confirm_with_sow_service(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    await hass.services.async_call(
        DOMAIN, "sow", {"plot": "A3", "crop": "sunflower", "date": "2026-11-02"}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.plot_a3_status").state == "planned"
    await hass.services.async_call(DOMAIN, "sow", {"plot": "A3"}, blocking=True)
    current, _ = manager.current("A3")
    assert not current.planned
    assert current.sown_on == TODAY  # confirmed today, so its dates count from today


async def test_get_tasks_returns_summaries(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    sow_unwatered(manager, ["A1"], "radish", "2026-10-25")
    result = await hass.services.async_call(DOMAIN, "get_tasks", {}, blocking=True, return_response=True)
    assert result["date"] == "2026-10-29"
    kinds = {t["kind"]: t for t in result["tasks"]}
    assert set(kinds) == {"uncover", "water"}
    assert kinds["uncover"]["summary"] == "Uncover Plot A1 (Radish)"
    assert kinds["uncover"]["late"] is True


async def test_water_all_button_and_plot_button(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    sow_unwatered(manager, ["A1", "A2"], "radish", "2026-10-27")
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.microgreens_watering_due").state == "on"
    await hass.services.async_call("button", "press", {"entity_id": "button.plot_a1_watered"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.plot_a1_needs_water").state == "off"
    assert hass.states.get("binary_sensor.plot_a2_needs_water").state == "on"
    await hass.services.async_call("button", "press", {"entity_id": "button.microgreens_water_all_due"}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get("binary_sensor.microgreens_watering_due").state == "off"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("button", "press", {"entity_id": "button.plot_a6_watered"}, blocking=True)


async def test_todo_lists_tasks_and_check_off_does_them(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    (planting,) = sow_unwatered(manager, ["A1"], "radish", "2026-10-25")
    await hass.async_block_till_done()
    items = await hass.services.async_call(
        TODO_DOMAIN, "get_items", {"entity_id": "todo.microgreens_tasks"}, blocking=True, return_response=True
    )
    summaries = sorted(i["summary"] for i in items["todo.microgreens_tasks"]["items"])
    assert summaries == ["Uncover Plot A1 (Radish)", "Water Plot A1 (Radish)"]
    assert hass.states.get("todo.microgreens_tasks").state == "2"
    await hass.services.async_call(
        TODO_DOMAIN,
        "update_item",
        {"entity_id": "todo.microgreens_tasks", "item": "Uncover Plot A1 (Radish)", "status": "completed"},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert planting.uncovered_on == TODAY
    assert hass.states.get("todo.microgreens_tasks").state == "1"


async def test_plot_added_and_deleted_follow_devices(hass: HomeAssistant, entry) -> None:
    manager = entry.runtime_data
    manager.save_plot({"id": "B1", "name": "Window", "location": "Kitchen"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.window_status").state == "empty"
    manager.save_plot({"id": "B1", "name": "Window sill"})
    await hass.async_block_till_done()
    device = dr.async_get(hass).async_get_device({(DOMAIN, f"{entry.entry_id}_B1")})
    assert device.name == "Window sill"
    manager.sow(["B1"], "radish")
    with pytest.raises(Exception) as err:
        manager.delete_plot("B1")
    assert err.value.key == "plot_in_use"
    manager.delete_plot("B1", force=True)
    await hass.async_block_till_done()
    assert dr.async_get(hass).async_get_device({(DOMAIN, f"{entry.entry_id}_B1")}) is None
    assert er.async_get(hass).async_get("sensor.window_status") is None
    assert hass.states.get("sensor.window_status") is None
    assert manager.data.history[-1].outcome == "discarded"
    # Same id again gets fresh entities.
    manager.save_plot({"id": "B1", "name": "Window"})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.window_status") is not None


async def test_midnight_rolls_status_forward(hass: HomeAssistant, entry, freezer) -> None:
    manager = entry.runtime_data
    sow_unwatered(manager, ["A1"], "radish", "2026-10-22")  # harvest window opens 2026-10-30
    manager.uncover(manager.current("A1")[0].id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.plot_a1_status").state == "growing"
    freezer.move_to("2026-10-30 00:00:02+01:00")
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.plot_a1_status").state == "ready"
    assert hass.states.get("sensor.microgreens_ready_to_harvest").state == "1"


async def test_data_survives_a_reload(hass: HomeAssistant, entry) -> None:
    entry.runtime_data.sow(["A4"], "mustard", label="batch-7")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    current, _ = entry.runtime_data.current("A4")
    assert current.label == "batch-7"


async def test_unload(hass: HomeAssistant, entry) -> None:
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(DOMAIN, "water", {}, blocking=True)
    assert err.value.translation_key == "not_loaded"


async def test_legacy_store_is_imported_once(hass: HomeAssistant, hass_storage, freezer) -> None:
    from .test_models import LEGACY

    freezer.move_to("2026-10-29 10:00:00+01:00")
    hass_storage["microgreens"] = {"version": 1, "minor_version": 1, "key": "microgreens", "data": LEGACY}
    entry = await setup_entry(hass)
    manager = entry.runtime_data
    assert [p.id for p in manager.data.plots] == ["A1", "A2", "A3"]
    assert manager.data.profile("rukola").name == "Rukola"
    assert hass.states.get("sensor.plot_a1_status").state == "growing"
    assert hass.states.get("sensor.plot_a2_status").state == "planned"
    # The old file is left as it was.
    assert hass_storage["microgreens"]["data"] == LEGACY


async def test_backdated_sowing_counts_as_watered_today(hass: HomeAssistant, entry) -> None:
    """Entering a tray sown last week must not report a week of missed watering."""
    (planting,) = entry.runtime_data.sow(["A1"], "radish", "2026-10-22")
    assert planting.last_watered_on == TODAY
    assert not any(t.kind == "water" for t in entry.runtime_data.tasks())
