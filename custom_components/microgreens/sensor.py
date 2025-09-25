from __future__ import annotations
from datetime import date
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from .const import DOMAIN, SIGNAL_DATA_UPDATED, SIGNAL_NEW_PLOT

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    rt = hass.data[DOMAIN][entry.entry_id]

    entities = [MicrogreensMetaSensor(rt)]
    for p in rt.data.plots:
        entities.append(MicrogreensPlotSensor(rt, p.id))
    async_add_entities(entities)

    @callback
    def _on_new_plot(plot_id: str):
        async_add_entities([MicrogreensPlotSensor(rt, plot_id)])
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW_PLOT, _on_new_plot))

class _Base(SensorEntity):
    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._rt.entry.entry_id)},
            name="Microgreens Manager",
            manufacturer="Custom"
        )

class MicrogreensMetaSensor(_Base):
    _attr_icon = "mdi:database-cog"
    _attr_unique_id = "microgreens_meta"
    _attr_name = "Microgreens Meta"

    def __init__(self, rt):
        self._rt = rt

    @property
    def native_value(self):
        return "ok"

    @property
    def extra_state_attributes(self):
        return {
            "profiles": [{
                "id": p.id, "name": p.name, "cover_days": p.cover_days,
                "uncover_days": p.uncover_days, "water": p.watering_frequency_days,
                "notes": p.notes
            } for p in self._rt.data.profiles],
            "plots": [{"id": p.id, "label": p.label} for p in self._rt.data.plots],
        }

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_DATA_UPDATED, self._upd))

    @callback
    def _upd(self):
        self.async_write_ha_state()

class MicrogreensPlotSensor(_Base):
    _attr_icon = "mdi:sprout"

    def __init__(self, rt, plot_id: str):
        self._rt = rt
        self._plot_id = plot_id
        self._attr_unique_id = f"{rt.entry.entry_id}_plot_{plot_id}"
        # IMPORTANT: name controls entity_id → sensor.microgreens_plot_<ID>
        self._attr_name = f"Microgreens Plot {plot_id}"

    @property
    def native_value(self):
        dep = next((d for d in self._rt.data.deployments if d.plot_id == self._plot_id), None)
        if not dep:
            return "idle"
        today = date.today()
        ce = date.fromisoformat(dep.cover_end)
        hv = date.fromisoformat(dep.harvest_date)
        if today < ce:
            return "covered"
        if today < hv:
            return "uncovered"
        return "mature"

    @property
    def extra_state_attributes(self):
        dep = next((d for d in self._rt.data.deployments if d.plot_id == self._plot_id), None)
        if not dep:
            return {
                "plot_id": self._plot_id, "sticker": "", "plant_id": "", "plant_name": "",
                "days_since_planting": 0, "cover_end": "", "harvest_date": "", "next_watering_due": "",
            }
        days = max(0, (date.today() - date.fromisoformat(dep.start_date)).days)
        return {
            "plot_id": dep.plot_id, "sticker": dep.sticker, "plant_id": dep.plant_id, "plant_name": dep.plant_name,
            "days_since_planting": days, "cover_end": dep.cover_end, "harvest_date": dep.harvest_date,
            "next_watering_due": dep.next_watering_due,
        }

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_DATA_UPDATED, self._upd))

    @callback
    def _upd(self):
        self.async_write_ha_state()
