"""Config flow, options flow and the legacy-entry repair."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import DOMAIN


async def test_user_flow_creates_one_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"]["digest_time"] == "08:00:00"
    await hass.async_block_till_done()
    again = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert again["type"] is FlowResultType.ABORT
    assert again["reason"] == "single_instance_allowed"


async def test_user_flow_carries_legacy_options(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain="microgreens",
        options={"notify_service": "notify.mobile_app_old", "summary_time": "06:30:00"},
    ).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["options"]["notify_targets"] == ["notify.mobile_app_old"]
    assert result["options"]["digest_time"] == "06:30:00"


async def test_options_flow(hass: HomeAssistant, entry, notify_calls) -> None:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert "notify_targets" in schema_keys
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "notify_targets": ["notify.mobile_app_phone"],
            "persistent_notification": False,
            "digest_enabled": True,
            "digest_time": "07:00:00",
            "reminder_enabled": False,
            "reminder_time": "20:00:00",
            "notification_actions": True,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.options["notify_targets"] == ["notify.mobile_app_phone"]
    assert entry.runtime_data.options["reminder_enabled"] is False


async def test_legacy_entry_repair_removes_it(hass: HomeAssistant, freezer, hass_client) -> None:
    from .conftest import setup_entry

    legacy = MockConfigEntry(domain="microgreens", title="Microgreens 0.1")
    legacy.add_to_hass(hass)
    await setup_entry(hass)
    issue = ir.async_get(hass).async_get_issue(DOMAIN, "legacy_entry")
    assert issue is not None and issue.is_fixable

    assert await async_setup_component(hass, "repairs", {})
    from homeassistant.components.repairs import repairs_flow_manager

    flow = await repairs_flow_manager(hass).async_init(DOMAIN, data={"issue_id": "legacy_entry"})
    assert flow["step_id"] == "confirm"
    done = await repairs_flow_manager(hass).async_configure(flow["flow_id"], {})
    assert done["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
