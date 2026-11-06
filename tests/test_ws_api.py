"""WebSocket API (ws_api.py) through Home Assistant's real WebSocket server."""
from __future__ import annotations

from homeassistant.core import HomeAssistant

from .conftest import sow_unwatered

DOMAIN = "ha_microgreens"


async def _ws(hass_ws_client, hass, **kw):
    client = await hass_ws_client(hass, **kw)
    counter = iter(range(1, 10_000))

    async def call(type_: str, **payload):
        await client.send_json({"id": next(counter), "type": f"{DOMAIN}/{type_}", **payload})
        return await client.receive_json()

    return client, call


async def test_snapshot_shape(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    sow_unwatered(entry.runtime_data, ["A1"], "radish", "2026-10-27")
    msg = await call("snapshot")
    assert msg["success"]
    snap = msg["result"]
    assert snap["today"] == "2026-10-29"
    assert [p["id"] for p in snap["plots"]][:2] == ["A1", "A2"]
    assert snap["plots"][0]["status"] == "covered"
    planting = snap["plantings"][0]
    assert planting["sown_on"] == "2026-10-27"
    assert planting["computed"]["harvest_start"] == "2026-11-04"
    assert {t["kind"] for t in snap["tasks"]} == {"water"}
    assert snap["notifications"]["digest_time"] == "08:00"


async def test_subscribe_pushes_after_each_change(hass: HomeAssistant, entry, hass_ws_client) -> None:
    client, call = await _ws(hass_ws_client, hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    first = await client.receive_json()
    assert first["event"]["loaded"] is True
    assert first["event"]["plantings"] == []
    entry.runtime_data.sow(["A2"], "pea")
    await hass.async_block_till_done()
    pushed = await client.receive_json()
    assert pushed["event"]["plots"][1]["status"] == "covered"


async def test_subscription_survives_an_entry_reload(hass: HomeAssistant, entry, hass_ws_client) -> None:
    client, _ = await _ws(hass_ws_client, hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    await client.receive_json()
    await client.receive_json()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    entry.runtime_data.sow(["A3"], "radish")
    await hass.async_block_till_done()
    statuses = None
    for _ in range(5):
        msg = await client.receive_json()
        if msg["event"].get("loaded") and msg["event"]["plots"][2]["status"] == "covered":
            statuses = msg["event"]["plots"][2]["status"]
            break
    assert statuses == "covered"


async def test_sow_action_and_refusal_codes(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    msg = await call("planting/sow", plot_ids=["A1", "A2"], profile_id="radish")
    assert msg["success"] and len(msg["result"]) == 2
    pid = msg["result"][0]
    assert (await call("planting/action", planting_id=pid, action="uncover"))["success"]
    msg = await call("planting/sow", plot_ids=["A1"], profile_id="pea")
    assert not msg["success"]
    assert msg["error"]["code"] == "plot_busy"
    assert msg["error"]["translation_placeholders"]["plot"] == "Plot A1"
    msg = await call("planting/action", planting_id=pid, action="harvest", yield_grams=120, rating=5)
    assert msg["success"] and msg["result"]["history_id"] == pid
    msg = await call("history/reopen", history_id=pid)
    assert msg["success"]
    assert entry.runtime_data.current("A1")[0].id == msg["result"]["planting_id"]


async def test_update_planting(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    (planting,) = entry.runtime_data.sow(["A1"], "radish")
    msg = await call("planting/update", planting_id=planting.id, changes={"light_days": 7, "plot_id": "A5", "notes": "moved"})
    assert msg["success"]
    updated = entry.runtime_data.data.planting(planting.id)
    assert (updated.plot_id, updated.crop.light_days, updated.notes) == ("A5", 7, "moved")
    msg = await call("planting/update", planting_id=planting.id, changes={"sown_on": "2027-01-01"})
    assert msg["error"]["code"] == "sown_in_future"


async def test_task_complete_and_water(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    (p,) = sow_unwatered(entry.runtime_data, ["A1"], "radish", "2026-10-25")
    assert (await call("task/complete", task_id=f"uncover:{p.id}"))["success"]
    assert (await call("water"))["result"] == {"watered": 1}
    assert entry.runtime_data.tasks() == []
    assert (await call("task/complete", task_id="bogus:x"))["error"]["code"] == "unknown_task"


async def test_profiles_plots_and_settings(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    msg = await call("profile/save", profile={"name": "Red cabbage", "cover_days": 2, "light_days": 9, "color": "#8E24AA"})
    assert msg["result"] == {"id": "red_cabbage"}
    assert entry.runtime_data.data.profile("red_cabbage").color == "#8e24aa"
    assert (await call("profile/save", profile={"name": "X", "light_days": 0}))["error"]["code"] == "invalid_number"
    assert (await call("plot/save", plot={"name": "Shelf 2 left"}))["result"] == {"id": "shelf_2_left"}
    ids = [p.id for p in entry.runtime_data.plots_sorted()]
    assert (await call("plot/reorder", plot_ids=list(reversed(ids))))["success"]
    assert entry.runtime_data.plots_sorted()[0].id == "shelf_2_left"
    msg = await call("settings/get")
    assert msg["result"]["options"]["digest_time"] == "08:00:00"
    msg = await call("settings/save", options={"digest_time": "06:15", "notify_targets": ["notify.x"]})
    assert msg["result"]["options"]["digest_time"] == "06:15:00"
    await hass.async_block_till_done()
    assert entry.options["notify_targets"] == ["notify.x"]
    assert entry.runtime_data.options["digest_time"] == "06:15:00"


async def test_backup_round_trip(hass: HomeAssistant, entry, hass_ws_client) -> None:
    _, call = await _ws(hass_ws_client, hass)
    entry.runtime_data.sow(["A1"], "radish")
    backup = (await call("backup/export"))["result"]
    assert backup["format"] == "ha_microgreens_backup"
    entry.runtime_data.delete_plot("A1", force=True)
    assert (await call("backup/import", backup=backup))["success"]
    await hass.async_block_till_done()
    assert entry.runtime_data.current("A1")[0] is not None
    assert hass.states.get("sensor.plot_a1_status").state == "covered"
    assert (await call("backup/import", backup={"format": "nope"}))["error"]["code"] == "invalid_backup"


async def test_admin_only_commands(hass: HomeAssistant, entry, hass_ws_client, hass_admin_user) -> None:
    hass_admin_user.groups = []  # now an ordinary user
    _, call = await _ws(hass_ws_client, hass)
    assert (await call("profile/save", profile={"name": "X"}))["error"]["code"] == "unauthorized"
    assert (await call("settings/get"))["error"]["code"] == "unauthorized"
    assert (await call("backup/export"))["error"]["code"] == "unauthorized"
    # Everyday tray work stays open to everyone.
    assert (await call("planting/sow", plot_ids=["A1"], profile_id="radish"))["success"]
    assert (await call("water"))["success"]
    assert (await call("snapshot"))["success"]


async def test_not_loaded(hass: HomeAssistant, entry, hass_ws_client) -> None:
    client, call = await _ws(hass_ws_client, hass)
    assert (await call("subscribe"))["success"]
    await client.receive_json()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert (await call("snapshot"))["error"]["code"] == "not_loaded"
