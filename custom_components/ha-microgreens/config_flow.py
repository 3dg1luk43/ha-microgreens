# custom_components/microgreens/config_flow.py
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant import config_entries
from homeassistant.helpers.selector import selector
from homeassistant.config_entries import ConfigEntry, OptionsFlow

from .const import (
    DOMAIN,
    DEFAULT_CALENDAR, DEFAULT_NOTIFY, DEFAULT_TITLE_PREFIX,
    DEFAULT_WATERING_TIME, DEFAULT_SUMMARY_TIME,
)

def _notify_choices(hass: HomeAssistant) -> list[str]:
    svcs = hass.services.async_services().get("notify", {}) or {}
    return [f"notify.{name}" for name in sorted(svcs.keys())]

def _calendar_choices(hass: HomeAssistant) -> list[str]:
    return sorted([s.entity_id for s in hass.states.async_all("calendar")])

class MicrogreensConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create single instance; settings are in Options (gear)."""
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        return self.async_create_entry(title="Microgreens", data={})

    async def async_step_import(self, user_input):
        return await self.async_step_user(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: ConfigEntry):
        self._entry = entry

    def _current(self, hass: HomeAssistant) -> dict[str, Any]:
        o = dict(self._entry.options)
        calendars = _calendar_choices(hass)
        notifies  = _notify_choices(hass)
        o.setdefault("calendar_entity", calendars[0] if calendars else DEFAULT_CALENDAR)
        o.setdefault("notify_service",  notifies[0]  if notifies  else DEFAULT_NOTIFY)
        o.setdefault("title_prefix",    DEFAULT_TITLE_PREFIX)
        o.setdefault("watering_time",   DEFAULT_WATERING_TIME)  # "HH:MM[:SS]"
        o.setdefault("summary_time",    DEFAULT_SUMMARY_TIME)
        return o

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        hass = self.hass
        cur  = self._current(hass)

        if user_input is not None:
            def _to_hms(v):
                from datetime import time as dtime
                if isinstance(v, dtime):
                    return f"{v.hour:02d}:{v.minute:02d}:{v.second:02d}"
                parts = str(v).split(":")
                if len(parts) == 2: parts.append("00")
                h, m, s = (int(parts[0]), int(parts[1]), int(parts[2]))
                return f"{h:02d}:{m:02d}:{s:02d}"

            data = {
                "calendar_entity": user_input["calendar_entity"],
                "notify_service":  user_input["notify_service"],
                "title_prefix":    user_input["title_prefix"],
                "watering_time":   _to_hms(user_input["watering_time"]),
                "summary_time":    _to_hms(user_input["summary_time"]),
            }
            return self.async_create_entry(title="", data=data)

        notify_opts = _notify_choices(hass)
        if notify_opts:
            notify_selector = selector({"select": {"options": notify_opts}})
            notify_default  = cur["notify_service"] if cur["notify_service"] in notify_opts else notify_opts[0]
        else:
            notify_selector = selector({"text": {}})
            notify_default  = cur["notify_service"]

        schema = vol.Schema({
            vol.Required("calendar_entity", default=cur["calendar_entity"]):
                selector({"entity": {"domain": "calendar"}}),
            vol.Required("notify_service",  default=notify_default): notify_selector,
            vol.Required("title_prefix",    default=cur["title_prefix"]):
                selector({"text": {}}),
            vol.Required("watering_time",   default=cur["watering_time"]):
                selector({"time": {}}),
            vol.Required("summary_time",    default=cur["summary_time"]):
                selector({"time": {}}),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
