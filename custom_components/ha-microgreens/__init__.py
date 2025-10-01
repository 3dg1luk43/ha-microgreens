from __future__ import annotations

import logging
from importlib import resources
import os
from dataclasses import dataclass, field, asdict
from dataclasses import fields as dc_fields
from datetime import date, time, timedelta
from datetime import time as dtime
from typing import Optional

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.const import Platform
from homeassistant.helpers import storage, dispatcher, event as ha_event
from homeassistant.components.http import StaticPathConfig

from .const import (
    DOMAIN, STORAGE_KEY, STORAGE_VERSION,
    SIGNAL_DATA_UPDATED, SIGNAL_NEW_PLOT,
    SIGNAL_REMOVE_PLOT,
    DEFAULT_CALENDAR, DEFAULT_NOTIFY, DEFAULT_TITLE_PREFIX,
    DEFAULT_WATERING_TIME, DEFAULT_SUMMARY_TIME, KEY_FRONTEND_BASE
)


PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]  # <-- add CALENDAR

_LOGGER = logging.getLogger(__name__)
_FRONTEND_URL_BASE = "/microgreens-frontend"  # static mount of packaged assets
_FRONTEND_FILES = ("microgreens-card.js", "microgreens-plot-card.js")
_WWW_SUBDIR = "ha-microgreens"               # -> served as /local/ha-microgreens/



# --------------------------- Data Model ---------------------------

@dataclass
class Profile:
    id: str
    name: str
    cover_days: int
    uncover_days: int
    watering_frequency_days: int = 1
    notes: str = ""


@dataclass
class Plot:
    id: str
    label: str


@dataclass
class Deployment:
    plot_id: str
    sticker: str
    plant_id: str
    plant_name: str
    start_date: str
    cover_end: str
    harvest_date: str
    watering_every_days: int
    next_watering_due: str
    notes: str = ""

@dataclass
class MicrogreensData:
    plots: list[Plot]
    profiles: list[Profile]
    deployments: list[Deployment]

    @classmethod
    def from_dict(cls, raw: dict | None) -> "MicrogreensData":
        raw = raw or {}
        d = cls(plots=[], profiles=[], deployments=[])
        for x in raw.get("plots", []):
            d.plots.append(Plot(**x))
        for x in raw.get("profiles", []):
            d.profiles.append(Profile(**x))
        valid = {f.name for f in dc_fields(Deployment)}
        for x in raw.get("deployments", []):
            x = {k: v for k, v in dict(x).items() if k in valid}
            d.deployments.append(Deployment(**x))
        return d

    def to_dict(self) -> dict:
        return {
            "plots": [asdict(p) for p in self.plots],
            "profiles": [asdict(p) for p in self.profiles],
            "deployments": [asdict(d) for d in self.deployments],
        }


class MicrogreensStore:
    def __init__(self, hass: HomeAssistant):
        self._store = storage.Store(hass, STORAGE_VERSION, STORAGE_KEY)

    async def async_load(self) -> MicrogreensData:
        raw = await self._store.async_load() or {}
        return MicrogreensData.from_dict(raw)

    async def async_save(self, data: MicrogreensData) -> None:
        await self._store.async_save(data.to_dict())

# --------------------------- Integration runtime ---------------------------

class Runtime:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.hass = hass
        self.entry = entry
        self.store = MicrogreensStore(hass)
        self.data = MicrogreensData(plots=[], profiles=[], deployments=[])
        self._unsubs: list[callable] = []

    # ---- options helpers
    @property
    def title_prefix(self) -> str:
        return self.entry.options.get("title_prefix", DEFAULT_TITLE_PREFIX)

    @property
    def calendar_entity(self) -> str:
        return self.entry.options.get("calendar_entity", DEFAULT_CALENDAR)

    @property
    def notify_service(self) -> str:
        return self.entry.options.get("notify_service", DEFAULT_NOTIFY)

    def _opt_time(self, key: str, default_str: str) -> time:
        """Return a datetime.time from options; accept time object or HH:MM[:SS] string."""
        v = self.entry.options.get(key, default_str)
        if isinstance(v, time):
            return v
        try:
            parts = [int(x) for x in str(v).split(":")]
        except Exception:
            parts = [int(x) for x in default_str.split(":")]
        while len(parts) < 3:
            parts.append(0)
        h, m, s = parts[:3]
        return time(hour=h, minute=m, second=s)

    @property
    def watering_time(self) -> time:
        return self._opt_time("watering_time", DEFAULT_WATERING_TIME)

    @property
    def summary_time(self) -> time:
        return self._opt_time("summary_time", DEFAULT_SUMMARY_TIME)

    # ---- lifecycle
    async def async_load(self):
        self.data = await self.store.async_load()
        if not self.data.plots:
            self.data.plots = [Plot(id=f"A{i}", label=f"Plot A{i}") for i in range(1, 7)]

        defaults = {
            "rukola":   Profile("rukola","Rukola",3,8,1),
            "koriandr": Profile("koriandr","Koriandr",6,19,1),
            "redkvicka":Profile("redkvicka","Ředkvička",4,10,1),
            "hrasek":   Profile("hrasek","Hrášek",5,16,1),
            "horcice":  Profile("horcice","Hořčice",3,11,1),
        }
        have = {p.id for p in self.data.profiles}
        added = False
        for k, v in defaults.items():
            if k not in have:
                self.data.profiles.append(v); added = True
        if added:
            _LOGGER.info("Seeded default profiles")
            await self.store.async_save(self.data)


    async def async_start(self):
        await self.async_load()
        self._schedule_jobs()
        self._register_services()
        _LOGGER.info("Microgreens started; %d profiles, %d plots, %d deployments",
            len(self.data.profiles), len(self.data.plots), len(self.data.deployments))

    async def async_stop(self):
        for u in self._unsubs:
            u()
        self._unsubs.clear()

    def _schedule_jobs(self):
        @callback
        def _summary_cb(now):
            self.hass.async_create_task(self._daily_summary())

        @callback
        def _water_cb(now):
            self.hass.async_create_task(self._watering_reminder())

        self._unsubs.append(
            ha_event.async_track_time_change(
                self.hass, _summary_cb,
                hour=self.summary_time.hour, minute=self.summary_time.minute, second=self.summary_time.second
            )
        )
        self._unsubs.append(
            ha_event.async_track_time_change(
                self.hass, _water_cb,
                hour=self.watering_time.hour, minute=self.watering_time.minute, second=self.watering_time.second
            )
        )

        @callback
        def _midnight_cb(now):
            dispatcher.async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)
        self._unsubs.append(
            ha_event.async_track_time_change(self.hass, _midnight_cb, hour=0, minute=0, second=0)
        )

    async def _save_and_broadcast(self):
        await self.store.async_save(self.data)
        dispatcher.async_dispatcher_send(self.hass, SIGNAL_DATA_UPDATED)

    # ---- CRUD
    async def add_or_update_profile(self, p: dict):
        if not p.get("id") or not p.get("name"):
            raise vol.Invalid("id and name are required")
        obj = Profile(
            id=p["id"], name=p["name"],
            cover_days=int(p.get("cover_days", 0)),
            uncover_days=int(p.get("uncover_days", 0)),
            watering_frequency_days=int(p.get("watering_frequency_days", 1)),
            notes=p.get("notes", ""),
        )
        existing = next((x for x in self.data.profiles if x.id == obj.id), None)
        if existing:
            self.data.profiles = [obj if x.id == obj.id else x for x in self.data.profiles]
            _LOGGER.info("Updated profile %s", obj.id)
        else:
            self.data.profiles.append(obj)
            _LOGGER.info("Added profile %s", obj.id)
        await self._save_and_broadcast()

    async def delete_profile(self, pid: str):
        self.data.profiles = [x for x in self.data.profiles if x.id != pid]
        _LOGGER.info("Deleted profile %s", pid)
        await self._save_and_broadcast()

    async def add_plot(self, plot_id: str, label: Optional[str] = None):
        if any(x.id == plot_id for x in self.data.plots):
            return
        self.data.plots.append(Plot(id=plot_id, label=label or plot_id))
        _LOGGER.info("Added plot %s", plot_id)
        await self._save_and_broadcast()
        dispatcher.async_dispatcher_send(self.hass, SIGNAL_NEW_PLOT, plot_id)

    async def remove_plot(self, plot_id: str):
        self.data.plots = [x for x in self.data.plots if x.id != plot_id]
        self.data.deployments = [d for d in self.data.deployments if d.plot_id != plot_id]
        _LOGGER.info("Removed plot %s", plot_id)
        await self._save_and_broadcast()
        # notify sensor platform to remove the entity
        dispatcher.async_dispatcher_send(self.hass, SIGNAL_REMOVE_PLOT, plot_id)

    # ----- in Runtime.deploy(): no calendar service call, just state update
    async def deploy(self, plot_id: str, profile_id: str, start_date: str, sticker: Optional[str] = None):
        from datetime import date as _date, timedelta
        prof = next((x for x in self.data.profiles if x.id == profile_id), None)
        if not prof:
            raise vol.Invalid("profile not found")

        sd = _date.fromisoformat(start_date)
        cover_end = sd + timedelta(days=prof.cover_days)
        harvest   = sd + timedelta(days=prof.cover_days + prof.uncover_days)
        next_water = sd + timedelta(days=max(1, prof.watering_frequency_days))

        # replace any existing dep for this plot
        self.data.deployments = [d for d in self.data.deployments if d.plot_id != plot_id]
        self.data.deployments.append(Deployment(
            plot_id=plot_id,
            sticker=sticker or plot_id,
            plant_id=prof.id,
            plant_name=prof.name,
            start_date=sd.isoformat(),
            cover_end=cover_end.isoformat(),
            harvest_date=harvest.isoformat(),
            watering_every_days=prof.watering_frequency_days,
            next_watering_due=next_water.isoformat(),
            notes=prof.notes,
        ))
        _LOGGER.info("Deployed %s on %s (start=%s)", prof.name, plot_id, sd.isoformat())
        await self._save_and_broadcast()

    # ----- in Runtime.harvest() / unassign(): just remove deployment
    async def harvest(self, plot_id: str):
        self.data.deployments = [d for d in self.data.deployments if d.plot_id != plot_id]
        _LOGGER.info("Harvested %s", plot_id)
        await self._save_and_broadcast()

    async def unassign(self, plot_id: str):
        await self.harvest(plot_id)

    # ---- helpers
    async def _notify(self, title: str, message: str):
        domain = "notify"
        try:
            service = self.notify_service.split(".")[1]
        except Exception:
            _LOGGER.warning("Invalid notify_service option '%s'", self.notify_service)
            return
        if not self.hass.services.has_service(domain, service):
            _LOGGER.warning("Notify service %s.%s not found; skipping", domain, service)
            return
        await self.hass.services.async_call(domain, service, {"title": title, "message": message}, blocking=False)

    async def _daily_summary(self):
        today = date.today().isoformat()
        phase_changes = []
        harvests = []
        for d in self.data.deployments:
            if d.cover_end == today:
                phase_changes.append(f"{d.plot_id} ({d.plant_name}) → uncover")
            if d.harvest_date == today:
                harvests.append(f"{d.plot_id} ({d.plant_name}) harvest")
        lines = []
        if phase_changes:
            lines.append("Phase changes today: " + ", ".join(phase_changes))
        if harvests:
            lines.append("Ready to harvest: " + ", ".join(harvests))
        if not lines:
            lines.append("No phase changes today.")
        await self._notify("Microgreens", "\n".join(lines))

    async def _watering_reminder(self):
        today = date.today()
        due = [d for d in self.data.deployments if date.fromisoformat(d.next_watering_due) <= today]
        if not due:
            return
        await self._notify("Microgreens", "Water today: " + ", ".join(f"{d.plot_id} ({d.plant_name})" for d in due))
        for d in due:
            d.next_watering_due = (date.fromisoformat(d.next_watering_due) + timedelta(days=max(1, d.watering_every_days))).isoformat()
        await self._save_and_broadcast()


# --------------------------- HA entry points ---------------------------

async def _register_static_frontend(hass: HomeAssistant) -> str:
    """Expose package 'frontend/' under a static URL and return the base url."""
    pkg_dir = resources.files(__package__) / "frontend"
    path = str(pkg_dir)

    # Guard to avoid duplicate registration across reloads
    flag = f"{DOMAIN}_static_registered"
    if hass.data.get(flag):
        return _FRONTEND_URL_BASE

    if hasattr(hass.http, "async_register_static_paths"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(_FRONTEND_URL_BASE, path, True)
        ])
    else:
        # Legacy fallback for old HA versions
        hass.http.register_static_path(_FRONTEND_URL_BASE, path, cache_headers=True)

    hass.data[flag] = True
    hass.data[KEY_FRONTEND_BASE] = _FRONTEND_URL_BASE
    _LOGGER.debug("Microgreens: registered static path %s -> %s", _FRONTEND_URL_BASE, path)
    return _FRONTEND_URL_BASE

def _copy_frontend_to_www(hass: HomeAssistant) -> str:
    """Copy JS modules to /config/www/ha-microgreens/ and return the /local base URL."""
    import shutil
    target = hass.config.path("www", _WWW_SUBDIR)
    os.makedirs(target, exist_ok=True)
    src_dir = resources.files(__package__) / "frontend"
    for name in _FRONTEND_FILES:
        with resources.as_file(src_dir / name) as src:
            shutil.copy2(str(src), os.path.join(target, name))
    base_url = f"/local/{_WWW_SUBDIR}"
    _LOGGER.info("Microgreens: frontend copied to %s/ (%s)", base_url, target)
    return base_url

def _inject_resources(hass: HomeAssistant, _static_base_url: str) -> None:
    """
    Ensure Lovelace loads our modules.

    Storage-mode dashboards will not show these as Resources rows; we use
    frontend.add_extra_module_url to load them at runtime.
    """
    try:
        local_base = _copy_frontend_to_www(hass)
        from homeassistant.components.frontend import add_extra_module_url
        for name in _FRONTEND_FILES:
            url = f"{local_base}/{name}"
            add_extra_module_url(hass, url)
            _LOGGER.debug("Microgreens: added Lovelace module (extra_url): %s", url)
    except Exception as exc:
        _LOGGER.warning(
            "Microgreens: could not auto-inject resources (%s). "
            "If needed, add Lovelace Resources manually to /local/%s/*.js",
            exc, _WWW_SUBDIR
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    base = await _register_static_frontend(hass)
    hass.data[KEY_FRONTEND_BASE] = base
    _inject_resources(hass, base)
    rt = Runtime(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = rt
    await rt.async_start()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    rt: Runtime = hass.data[DOMAIN][entry.entry_id]
    await rt.async_stop()
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


# --------------------------- Services ---------------------------

SERVICE_PROFILE_SCHEMA = vol.Schema({
    vol.Required("id"): str,
    vol.Required("name"): str,
    vol.Required("cover_days"): vol.Coerce(int),
    vol.Required("uncover_days"): vol.Coerce(int),
    vol.Optional("watering_frequency_days", default=1): vol.Coerce(int),
    vol.Optional("notes", default=""): str,
})

SERVICE_DEPLOY_SCHEMA = vol.Schema({
    vol.Required("plot_id"): str,
    vol.Required("profile_id"): str,
    vol.Required("start_date"): str,   # YYYY-MM-DD
    vol.Optional("sticker"): str,
})

SERVICE_PLOT_SCHEMA = vol.Schema({
    vol.Required("plot_id"): str,
    vol.Optional("label"): str,
})

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

def _rt(hass: HomeAssistant) -> Runtime:
    entry_id = next(iter(hass.data.get(DOMAIN, {})))
    return hass.data[DOMAIN][entry_id]

def _register_services(self: Runtime):
    hass = self.hass if hasattr(self, "_hass") else self.hass  # whatever you already use
    base = hass.data.get(KEY_FRONTEND_BASE, _FRONTEND_URL_BASE)
    _inject_resources(hass, base)

    async def profile_upsert(call: ServiceCall):
        _LOGGER.debug("Service profile_upsert: %s", call.data)
        await self.add_or_update_profile(dict(call.data))

    async def profile_delete(call: ServiceCall):
        _LOGGER.debug("Service profile_delete: %s", call.data)
        await self.delete_profile(call.data["id"])

    async def plot_add(call: ServiceCall):
        _LOGGER.debug("Service plot_add: %s", call.data)
        await self.add_plot(call.data["plot_id"], call.data.get("label"))

    async def plot_remove(call: ServiceCall):
        _LOGGER.debug("Service plot_remove: %s", call.data)
        await self.remove_plot(call.data["plot_id"])

    async def deploy(call: ServiceCall):
        _LOGGER.debug("Service deploy: %s", call.data)
        await self.deploy(
            call.data["plot_id"], call.data["profile_id"],
            call.data["start_date"], call.data.get("sticker")
        )

    async def _svc_reinstall_frontend(call):
        base = await _register_static_frontend(hass)
        hass.data[KEY_FRONTEND_BASE] = base
        _inject_resources(hass, base)

    async def harvest(call: ServiceCall):
        _LOGGER.debug("Service harvest: %s", call.data)
        await self.harvest(call.data["plot_id"])

    async def unassign(call: ServiceCall):
        _LOGGER.debug("Service unassign: %s", call.data)
        await self.unassign(call.data["plot_id"])

    hass.services.async_register(DOMAIN, "profile_upsert", profile_upsert, schema=SERVICE_PROFILE_SCHEMA)
    hass.services.async_register(DOMAIN, "profile_delete", profile_delete, schema=vol.Schema({vol.Required("id"): str}))
    hass.services.async_register(DOMAIN, "plot_add", plot_add, schema=SERVICE_PLOT_SCHEMA)
    hass.services.async_register(DOMAIN, "plot_remove", plot_remove, schema=vol.Schema({vol.Required("plot_id"): str}))
    hass.services.async_register(DOMAIN, "deploy", deploy, schema=SERVICE_DEPLOY_SCHEMA)
    hass.services.async_register(DOMAIN, "harvest", harvest, schema=vol.Schema({vol.Required("plot_id"): str}))
    hass.services.async_register(DOMAIN, "unassign", unassign, schema=vol.Schema({vol.Required("plot_id"): str}))
    hass.services.async_register(DOMAIN, "reinstall_frontend", _svc_reinstall_frontend)

    async def shift_schedule(call):
        from datetime import date as _date, timedelta
        pid = call.data["plot_id"]; delta = int(call.data["days"])
        d = next((x for x in self.data.deployments if x.plot_id == pid), None)
        if not d:
            return
        def sh(v): return (_date.fromisoformat(v) + timedelta(days=delta)).isoformat()
        d.start_date = sh(d.start_date)
        d.cover_end = sh(d.cover_end)
        d.harvest_date = sh(d.harvest_date)
        d.next_watering_due = sh(d.next_watering_due)
        await self._save_and_broadcast()

    hass.services.async_register(
        DOMAIN, "shift_schedule", shift_schedule,
        schema=vol.Schema({vol.Required("plot_id"): str, vol.Required("days"): vol.Coerce(int)})
    )


    async def seed_defaults(call: ServiceCall):
        await self.async_load()  # will fill any missing defaults
        await self._save_and_broadcast()
    hass.services.async_register(DOMAIN, "seed_defaults", seed_defaults)


    async def plot_rename(call: ServiceCall):
        pid = call.data["plot_id"]; label = call.data["label"]
        for p in self.data.plots:
            if p.id == pid: p.label = label
        _LOGGER.info("Renamed plot %s -> %s", pid, label)
        await self._save_and_broadcast()

    hass.services.async_register(DOMAIN, "shift_schedule", shift_schedule, schema=vol.Schema({
        vol.Required("plot_id"): str, vol.Required("days"): vol.Coerce(int)
    }))
    hass.services.async_register(DOMAIN, "plot_rename", plot_rename, schema=vol.Schema({
        vol.Required("plot_id"): str, vol.Required("label"): str
    }))


Runtime._register_services = _register_services
