from __future__ import annotations
from datetime import datetime, timedelta, date as _date
import homeassistant.util.dt as dt_util

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, SIGNAL_DATA_UPDATED

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    rt = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([MicrogreensCalendar(rt)])

class MicrogreensCalendar(CalendarEntity):
    _attr_name = "Microgreens"
    _attr_unique_id = "microgreens_calendar"
    _attr_icon = "mdi:calendar-range"

    def __init__(self, rt):
        self._rt = rt
        self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._rt.entry.entry_id)},
            name="Microgreens Manager",
            manufacturer="Custom",
        )

    @property
    def event(self):
        """Next upcoming event (optional)."""
        tz = dt_util.get_time_zone(self._rt.hass.config.time_zone)
        now = dt_util.now().astimezone(tz)
        candidates = []
        for d in self._rt.data.deployments:
            s = datetime.combine(_date.fromisoformat(d.start_date), datetime.min.time(), tzinfo=tz)
            e = datetime.combine(_date.fromisoformat(d.harvest_date) + timedelta(days=1), datetime.min.time(), tzinfo=tz)
            if e >= now:
                candidates.append((s, e, d))
        if not candidates:
            return None
        s, e, d = sorted(candidates, key=lambda x: x[0])[0]
        return CalendarEvent(summary=f"{self._rt.title_prefix} {d.plant_name} @ {d.plot_id}", start=s, end=e, description=d.notes)

    async def async_get_events(self, hass, start_date, end_date):
        """Return events between start_date and end_date (datetime aware)."""
        tz = dt_util.get_time_zone(hass.config.time_zone)
        events = []
        for d in self._rt.data.deployments:
            s = datetime.combine(_date.fromisoformat(d.start_date), datetime.min.time(), tzinfo=tz)
            e = datetime.combine(_date.fromisoformat(d.harvest_date) + timedelta(days=1), datetime.min.time(), tzinfo=tz)
            if e <= start_date or s >= end_date:
                continue
            summary = f"{self._rt.title_prefix} {d.plant_name} @ {d.plot_id}"
            desc = f"Start: {d.start_date}\nCovered until: {d.cover_end}\nHarvest: {d.harvest_date}\nSticker: {d.sticker}\n{d.notes or ''}".strip()
            events.append(CalendarEvent(summary=summary, start=s, end=e, description=desc))
        return events

    async def async_added_to_hass(self):
        self._unsub = async_dispatcher_connect(self.hass, SIGNAL_DATA_UPDATED, self._update)
        self.async_on_remove(self._unsub)

    def _update(self):
        # Use thread-safe scheduling to update state from signal callbacks
        # to avoid calling async_write_ha_state from non-loop threads.
        self.schedule_update_ha_state()
