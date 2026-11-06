"""Panel and card registration (frontend.py). The frontend component is not
installed in the test environment, so its three calls are recorded instead."""
from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.ha_microgreens import frontend
from custom_components.ha_microgreens.const import CARD_JS, PANEL_JS, PANEL_URL_PATH, STATIC_URL_BASE


@pytest.fixture
def fake_frontend(hass: HomeAssistant, monkeypatch):
    calls: dict[str, list] = {"panels": [], "removed": [], "extra": set()}
    module = types.ModuleType("homeassistant.components.frontend")
    module.async_register_built_in_panel = lambda hass, **kw: calls["panels"].append(kw)
    module.async_remove_panel = lambda hass, path, **kw: calls["removed"].append(path)
    module.add_extra_js_url = lambda hass, url: calls["extra"].add(url)
    module.remove_extra_js_url = lambda hass, url: calls["extra"].remove(url)
    monkeypatch.setitem(sys.modules, "homeassistant.components.frontend", module)
    import homeassistant.components as components

    monkeypatch.setattr(components, "frontend", module, raising=False)
    hass.config.components.add("frontend")
    monkeypatch.setattr(hass, "http", types.SimpleNamespace(async_register_static_paths=AsyncMock()))
    return calls


async def test_registers_panel_card_and_static_path(hass: HomeAssistant, fake_frontend) -> None:
    await frontend.async_setup(hass)
    (static,) = hass.http.async_register_static_paths.await_args.args[0]
    assert static.url_path == STATIC_URL_BASE and static.path == str(frontend.WWW)
    (panel,) = fake_frontend["panels"]
    assert panel["frontend_url_path"] == PANEL_URL_PATH
    custom = panel["config"]["_panel_custom"]
    version = frontend.served_report(hass)["version"]
    assert custom["module_url"] == f"{STATIC_URL_BASE}/{PANEL_JS}?v={version}"
    assert fake_frontend["extra"] == {f"{STATIC_URL_BASE}/{CARD_JS}?v={version}"}
    # A second setup (entry reload) registers nothing twice.
    await frontend.async_setup(hass)
    assert len(fake_frontend["panels"]) == 1
    assert hass.http.async_register_static_paths.await_count == 1


async def test_teardown_removes_panel_and_card(hass: HomeAssistant, fake_frontend) -> None:
    await frontend.async_setup(hass)
    frontend.async_teardown(hass)
    assert fake_frontend["removed"] == [PANEL_URL_PATH]
    assert fake_frontend["extra"] == set()
    await frontend.async_setup(hass)
    assert len(fake_frontend["panels"]) == 2


def test_build_version_changes_with_assets(tmp_path) -> None:
    (tmp_path / "a.js").write_text("one")
    first = frontend.build_version(tmp_path)
    (tmp_path / "a.js").write_text("two")
    assert frontend.build_version(tmp_path) != first


async def test_legacy_resources_are_removed(hass: HomeAssistant, fake_frontend, monkeypatch) -> None:
    from homeassistant.components.lovelace.resources import ResourceStorageCollection

    items = [
        {"id": "1", "url": "/ha-microgreens/microgreens-card.js?v=1", "res_type": "module"},
        {"id": "2", "url": "/local/ha-microgreens/microgreens-plot-card.js", "res_type": "module"},
        {"id": "3", "url": "/hacsfiles/other-card.js", "res_type": "module"},
    ]

    class FakeResources(ResourceStorageCollection):
        def __init__(self):  # noqa: D401 - no store needed
            pass

        async def async_get_info(self):
            return {}

        def async_items(self):
            return list(items)

        async def async_delete_item(self, item_id):
            items[:] = [i for i in items if i["id"] != item_id]

    hass.data["lovelace"] = types.SimpleNamespace(resources=FakeResources())
    hass.config.components.add("lovelace")
    await frontend.async_setup(hass)
    await hass.async_block_till_done()
    assert [i["id"] for i in items] == ["3"]
    assert frontend.served_report(hass)["legacy_resources_removed"] == 2
