from __future__ import annotations
from datetime import date
from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_registry as er
from .const import DOMAIN, SIGNAL_DATA_UPDATED, SIGNAL_NEW_PLOT, SIGNAL_REMOVE_PLOT


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    rt = hass.data[DOMAIN][entry.entry_id]

    # book-keeping of plot entities we create
    created: dict[str, MicrogreensPlotSensor] = {}

    # seed entities
    ents = [MicrogreensMetaSensor(rt)]
    for p in rt.data.plots:
        e = MicrogreensPlotSensor(rt, p.id)
        created[p.id] = e
        ents.append(e)
    async_add_entities(ents)

    # handle dynamic add
    @callback
    def _on_new_plot(plot_id: str):
        if plot_id in created:
            return
        e = MicrogreensPlotSensor(rt, plot_id)
        created[plot_id] = e
        async_add_entities([e])

    # handle dynamic remove
    @callback
    def _on_remove_plot(plot_id: str):
        # 1) remove the running entity
        ent = created.pop(plot_id, None)
        if ent:
            ent.async_remove()

        # 2) purge entity registry entry (so it doesn’t linger as orphan)
        reg = er.async_get(hass)
        unique_id = f"{rt.entry.entry_id}_plot_{plot_id}"
        ent_id = reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if ent_id:
            reg.async_remove(ent_id)

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_NEW_PLOT, _on_new_plot))
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_REMOVE_PLOT, _on_remove_plot))

    # --- one-time startup cleanup: purge registry entries for plots that no longer exist
    reg = er.async_get(hass)
    existing_plots = {p.id for p in rt.data.plots}
    # iterate over all registry entries for this integration+platform
    for ent_entry in list(reg.entities.values()):
        if ent_entry.domain != "sensor" or ent_entry.platform != DOMAIN:
            continue
        # our unique_id format: "<entry_id>_plot_<plot_id>"
        if not ent_entry.unique_id.startswith(f"{entry.entry_id}_plot_"):
            continue
        plot_id = ent_entry.unique_id.split("_plot_", 1)[-1]
        if plot_id not in existing_plots:
            reg.async_remove(ent_entry.entity_id)


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
