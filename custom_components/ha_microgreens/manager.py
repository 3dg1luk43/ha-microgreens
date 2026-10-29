# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The integration's runtime: data, writes, timers and notification delivery.

Every write is a synchronous method that validates first and changes nothing
when it raises :class:`MicrogreensError`, then calls :meth:`_changed`, which
schedules the store write and one coalesced push to entities and panels.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, replace
from datetime import date, timedelta
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.helpers.translation import async_get_translations
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTIONS,
    CONF_DIGEST_ENABLED,
    CONF_DIGEST_TIME,
    CONF_NOTIFY_TARGETS,
    CONF_PERSISTENT,
    CONF_REMINDER_ENABLED,
    CONF_REMINDER_TIME,
    DEFAULT_OPTIONS,
    DEFAULT_PLOT_COUNT,
    DEFAULT_PROFILES,
    DOMAIN,
    LEGACY_STORAGE_KEY,
    LEGACY_STORAGE_VERSION,
    MAX_NAME_LEN,
    MAX_NOTES_LEN,
    MAX_PLOTS,
    MAX_PROFILES,
    MAX_STAGE_DAYS,
    MAX_YIELD_G,
    OUTCOME_DISCARDED,
    OUTCOME_HARVESTED,
    PANEL_URL_PATH,
    PERSISTENT_NOTIFICATION_ID,
    PROFILE_PALETTE,
    SAVE_DELAY_S,
    SIGNAL_PLOTS_CHANGED,
    SIGNAL_UPDATED,
    STATUS_EMPTY,
    STORAGE_KEY,
    STORAGE_VERSION,
    TASK_HARVEST,
    TASK_SOAK,
    TASK_SOW,
    TASK_UNCOVER,
    TASK_WATER,
)
from .models import (
    Crop,
    GardenData,
    HistoryEntry,
    MicrogreensError,
    Planting,
    Plot,
    Profile,
    clean_date,
    clean_int,
    clean_name,
    clean_optional_float,
    clean_plot,
    clean_profile,
    clean_rating,
    clean_reason,
    clean_stage_numbers,
    clean_text,
    migrate_legacy,
    new_id,
    to_jsonable,
)
from .notification_rules import (
    KIND_DIGEST,
    KIND_REMINDER,
    KIND_TEST,
    Notice,
    build_notice,
    fmt,
    is_mobile_target,
    mobile_data,
    normalize_options,
    parse_time,
    task_summary,
    water_all_action,
)
from . import schedule

_LOGGER = logging.getLogger(__name__)

EVENT_MOBILE_ACTION = "mobile_app_notification_action"
BACKUP_FORMAT = "ha_microgreens_backup"
BACKUP_VERSION = 1


def loaded_manager(hass: HomeAssistant) -> MicrogreensManager | None:
    """The loaded entry's manager, if any (the integration allows one entry)."""
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        return entry.runtime_data
    return None


class MicrogreensManager:
    """One per config entry (the integration allows a single entry)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        version: str = "",
        listeners: set[Callable[[], None]] | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.version = version
        self.hub_device_id: str | None = None
        self.data = GardenData()
        self.options: dict[str, Any] = normalize_options(entry.options)
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._strings: dict[str, str] = {}
        self._timers: list[CALLBACK_TYPE] = []
        self._unsubs: list[CALLBACK_TYPE] = []
        # Owned by the domain, not the entry, so a panel subscribed before an
        # entry reload keeps receiving pushes from the new manager.
        self._listeners: set[Callable[[], None]] = listeners if listeners is not None else set()
        self._push_pending = False
        self._persistent_tasks: tuple[str, ...] | None = None
        self._warned_targets: set[str] = set()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    async def async_setup(self) -> None:
        await self._async_load_strings()
        raw = await self._store.async_load()
        if raw is None:
            self.data = await self._async_initial_data()
            await self._store.async_save(self.data.to_store())
        else:
            self.data = GardenData.from_store(raw)
        self._schedule_timers()
        self._unsubs.append(self.hass.bus.async_listen(EVENT_MOBILE_ACTION, self._on_mobile_action))
        _LOGGER.debug(
            "Loaded %d plots, %d crops, %d plantings, %d history entries",
            len(self.data.plots),
            len(self.data.profiles),
            len(self.data.plantings),
            len(self.data.history),
        )

    async def async_unload(self) -> None:
        for unsub in (*self._timers, *self._unsubs):
            unsub()
        self._timers.clear()
        self._unsubs.clear()
        # A pending delayed write must not be lost when the entry is reloaded.
        await self._store.async_save(self.data.to_store())

    async def _async_initial_data(self) -> GardenData:
        """First setup: import 0.1.x data if there is any, else seed defaults."""
        legacy = await Store(self.hass, LEGACY_STORAGE_VERSION, LEGACY_STORAGE_KEY).async_load()
        if legacy:
            data = migrate_legacy(legacy, self.today())
            _LOGGER.info(
                "Imported Microgreens 0.1 data: %d plots, %d crops, %d plantings "
                "(the old .storage/%s file is left as it was)",
                len(data.plots),
                len(data.profiles),
                len(data.plantings),
                LEGACY_STORAGE_KEY,
            )
            if data.plots or data.profiles:
                return data
        data = GardenData(meta={"seeded_on": self.today().isoformat()})
        for i, (key, soak, cover, light, window, water) in enumerate(DEFAULT_PROFILES):
            data.profiles.append(
                Profile(
                    id=key,
                    name=self._strings.get(f"crop_{key}", key.title())[:MAX_NAME_LEN],
                    color=PROFILE_PALETTE[i % len(PROFILE_PALETTE)],
                    soak_hours=soak,
                    cover_days=cover,
                    light_days=light,
                    harvest_window_days=window,
                    water_every_days=water,
                )
            )
        for i in range(DEFAULT_PLOT_COUNT):
            pid = f"A{i + 1}"
            data.plots.append(Plot(id=pid, name=fmt(self._strings, "default_plot_name", id=pid), order=i))
        return data

    async def _async_load_strings(self) -> None:
        """``common`` strings in the server language, English underneath."""
        prefix = f"component.{DOMAIN}.common."
        merged: dict[str, str] = {}
        language = self.hass.config.language or "en"
        for lang in dict.fromkeys(("en", language)):
            try:
                raw = await async_get_translations(self.hass, lang, "common", {DOMAIN})
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Could not load %s strings", lang)
                continue
            merged.update({k[len(prefix) :]: v for k, v in raw.items() if k.startswith(prefix)})
        self._strings = merged

    @callback
    def async_apply_options(self) -> None:
        """Options changed (options flow or panel): re-arm timers, no reload."""
        self.options = normalize_options(self.entry.options)
        self._schedule_timers()
        self._changed()

    def _schedule_timers(self) -> None:
        for unsub in self._timers:
            unsub()
        self._timers = []
        h, m, s = parse_time(self.options[CONF_DIGEST_TIME], DEFAULT_OPTIONS[CONF_DIGEST_TIME])
        self._timers.append(async_track_time_change(self.hass, self._on_digest_time, hour=h, minute=m, second=s))
        h, m, s = parse_time(self.options[CONF_REMINDER_TIME], DEFAULT_OPTIONS[CONF_REMINDER_TIME])
        self._timers.append(async_track_time_change(self.hass, self._on_reminder_time, hour=h, minute=m, second=s))
        # Statuses are date-driven: push a fresh snapshot just after midnight.
        self._timers.append(async_track_time_change(self.hass, self._on_midnight, hour=0, minute=0, second=1))

    @callback
    def _on_digest_time(self, _now: Any) -> None:
        if self.options[CONF_DIGEST_ENABLED]:
            self.entry.async_create_background_task(
                self.hass, self.async_send_digest(), f"{DOMAIN}_digest"
            )

    @callback
    def _on_reminder_time(self, _now: Any) -> None:
        if self.options[CONF_REMINDER_ENABLED]:
            self.entry.async_create_background_task(
                self.hass, self.async_send_reminder(), f"{DOMAIN}_reminder"
            )

    @callback
    def _on_midnight(self, _now: Any) -> None:
        self._changed(save=False)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #

    def today(self) -> date:
        """Today in Home Assistant's time zone (never the host's)."""
        return dt_util.now().date()

    def tasks(self) -> list[schedule.Task]:
        return schedule.tasks(self.data.plantings, self.data.plots, self.today())

    def plots_sorted(self) -> list[Plot]:
        return sorted(self.data.plots, key=lambda p: p.order)

    def current(self, plot_id: str) -> tuple[Planting | None, Planting | None]:
        return schedule.current_for_plot(self.data.plantings, plot_id)

    def plot_status(self, plot_id: str) -> str:
        return schedule.plot_status(self.data.plantings, plot_id, self.today())

    def task_summary(self, task: schedule.Task) -> str:
        return task_summary(task, self._plantings_by_id(), self._plots_by_id(), self._strings)

    def snapshot(self) -> dict[str, Any]:
        """Everything the panel and the card render, JSON-ready."""
        today = self.today()
        plots = []
        for plot in self.plots_sorted():
            cur, nxt = self.current(plot.id)
            plots.append(
                {
                    **asdict(plot),
                    "status": schedule.status(cur, today) if cur else STATUS_EMPTY,
                    "current": cur.id if cur else None,
                    "next": nxt.id if nxt else None,
                }
            )
        plantings = []
        for p in sorted(self.data.plantings, key=lambda x: x.sown_on):
            row = to_jsonable(asdict(p))
            row["computed"] = schedule.computed(p, today)
            plantings.append(row)
        history = sorted(self.data.history, key=lambda h: (h.ended_on, h.sown_on), reverse=True)
        return {
            "today": today.isoformat(),
            "version": self.version,
            "plots": plots,
            "profiles": [asdict(p) for p in self.data.profiles],
            "plantings": plantings,
            "tasks": [t.as_dict() for t in self.tasks()],
            "history": [to_jsonable(asdict(h)) for h in history],
            "notifications": {
                "targets": len(self.options[CONF_NOTIFY_TARGETS]),
                "persistent": self.options[CONF_PERSISTENT],
                "digest": self.options[CONF_DIGEST_ENABLED],
                "digest_time": self.options[CONF_DIGEST_TIME][:5],
                "reminder": self.options[CONF_REMINDER_ENABLED],
                "reminder_time": self.options[CONF_REMINDER_TIME][:5],
            },
        }

    # ------------------------------------------------------------------ #
    # Change propagation
    # ------------------------------------------------------------------ #

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.add(listener)

        @callback
        def _remove() -> None:
            self._listeners.discard(listener)

        return _remove

    @callback
    def _changed(self, *, save: bool = True, plots: bool = False) -> None:
        if save:
            self._store.async_delay_save(self.data.to_store, SAVE_DELAY_S)
        if plots:
            self._sync_devices()
            async_dispatcher_send(self.hass, SIGNAL_PLOTS_CHANGED.format(self.entry.entry_id))
        if not self._push_pending:
            # Several writes in one loop iteration (water all) push once.
            self._push_pending = True
            self.hass.loop.call_soon(self._push)

    @callback
    def _push(self) -> None:
        self._push_pending = False
        async_dispatcher_send(self.hass, SIGNAL_UPDATED.format(self.entry.entry_id))
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Microgreens listener failed")
        self._refresh_persistent()

    @callback
    def _sync_devices(self) -> None:
        """Remove devices of deleted plots, rename those of renamed ones."""
        registry = dr.async_get(self.hass)
        names = {f"{self.entry.entry_id}_{p.id}": p.name for p in self.data.plots}
        for device in dr.async_entries_for_config_entry(registry, self.entry.entry_id):
            ident = next((i[1] for i in device.identifiers if i[0] == DOMAIN), None)
            if ident is None or ident == self.entry.entry_id:
                continue  # the hub
            if ident not in names:
                registry.async_update_device(device.id, remove_config_entry_id=self.entry.entry_id)
            elif device.name != names[ident]:
                registry.async_update_device(device.id, name=names[ident])

    # ------------------------------------------------------------------ #
    # Crops
    # ------------------------------------------------------------------ #

    @callback
    def save_profile(self, raw: Mapping[str, Any]) -> Profile:
        profile = clean_profile(raw, self.data.profiles)
        existing = self.data.profile(profile.id)
        if existing is None:
            if len(self.data.profiles) >= MAX_PROFILES:
                raise MicrogreensError("too_many", max=MAX_PROFILES)
            self.data.profiles.append(profile)
        else:
            self.data.profiles[self.data.profiles.index(existing)] = profile
        self._changed()
        return profile

    @callback
    def delete_profile(self, profile_id: str) -> None:
        profile = self._profile(profile_id)
        # Plantings keep their own snapshot of the numbers, so they are fine.
        self.data.profiles.remove(profile)
        self._changed()

    # ------------------------------------------------------------------ #
    # Plots
    # ------------------------------------------------------------------ #

    @callback
    def save_plot(self, raw: Mapping[str, Any]) -> Plot:
        plot, created = clean_plot(raw, self.data.plots)
        if created:
            if len(self.data.plots) >= MAX_PLOTS:
                raise MicrogreensError("too_many", max=MAX_PLOTS)
            self.data.plots.append(plot)
        else:
            existing = self._plot(plot.id)
            self.data.plots[self.data.plots.index(existing)] = plot
        self._changed(plots=True)
        return plot

    @callback
    def delete_plot(self, plot_id: str, *, force: bool = False) -> None:
        plot = self._plot(plot_id)
        mine = [p for p in self.data.plantings if p.plot_id == plot_id]
        if mine and not force:
            raise MicrogreensError("plot_in_use", plot=plot.name)
        today = self.today()
        for planting in mine:
            if not planting.planned:
                self.data.history.append(self._history_from(planting, OUTCOME_DISCARDED, today, reason="other"))
            self.data.plantings.remove(planting)
        self.data.plots.remove(plot)
        self._changed(plots=True)

    @callback
    def reorder_plots(self, plot_ids: Iterable[str]) -> None:
        order = list(plot_ids)
        if sorted(order) != sorted(p.id for p in self.data.plots):
            raise MicrogreensError("invalid_order")
        position = {pid: i for i, pid in enumerate(order)}
        self.data.plots = sorted(
            (replace(p, order=position[p.id]) for p in self.data.plots), key=lambda p: p.order
        )
        self._changed()

    # ------------------------------------------------------------------ #
    # Plantings
    # ------------------------------------------------------------------ #

    @callback
    def sow(
        self,
        plot_ids: Iterable[str],
        profile_id: str,
        sown_on: Any = None,
        *,
        label: str = "",
        notes: str = "",
    ) -> list[Planting]:
        """Sow (date today or earlier) or plan (later date) ``profile_id`` on plots."""
        profile = self._profile(profile_id)
        today = self.today()
        day = clean_date(sown_on, "sown_on") if sown_on else today
        plot_ids = list(dict.fromkeys(plot_ids))
        if not plot_ids:
            raise MicrogreensError("no_plot")
        label = clean_text(label, MAX_NAME_LEN)
        notes = clean_text(notes)
        planned = day > today
        new: list[Planting] = []
        for plot_id in plot_ids:
            plot = self._plot(plot_id)
            planting = Planting(
                id=new_id(),
                plot_id=plot.id,
                profile_id=profile.id,
                crop=Crop.from_profile(profile),
                sown_on=day,
                planned=planned,
                label=label or f"{plot.id}-{day:%y%m%d}",
                notes=notes,
                # A tray entered after the fact has been looked after until now.
                last_watered_on=None if planned else today,
            )
            self._check_free(planting)
            new.append(planting)
        self.data.plantings.extend(new)
        self._changed()
        return new

    @callback
    def update_planting(self, planting_id: str, changes: Mapping[str, Any]) -> Planting:
        current = self._planting(planting_id)
        today = self.today()
        updated = replace(current)
        if "plot_id" in changes:
            updated.plot_id = self._plot(changes["plot_id"]).id
        if "sown_on" in changes:
            updated.sown_on = clean_date(changes["sown_on"], "sown_on")
            if not updated.planned and updated.sown_on > today:
                raise MicrogreensError("sown_in_future")
        if "label" in changes:
            updated.label = clean_text(changes["label"], MAX_NAME_LEN)
        if "notes" in changes:
            updated.notes = clean_text(changes["notes"])
        if "crop_name" in changes:
            updated.crop = replace(updated.crop, name=clean_name(changes["crop_name"]))
        numbers = clean_stage_numbers(changes, updated.crop)
        updated.crop = replace(updated.crop, **numbers)
        for key in ("uncovered_on", "last_watered_on"):
            if key in changes:
                value = changes[key]
                day = clean_date(value, key) if value else None
                if day is not None and (day < updated.sown_on or day > today):
                    raise MicrogreensError("invalid_date", field=key)
                setattr(updated, key, day)
        self._check_free(updated, ignore=current.id)
        self.data.plantings[self.data.plantings.index(current)] = updated
        self._changed()
        return updated

    @callback
    def soak(self, planting_id: str) -> Planting:
        planting = self._planting(planting_id)
        if not planting.planned:
            raise MicrogreensError("already_sown")
        planting.soaked_on = self.today()
        self._changed()
        return planting

    @callback
    def confirm_sown(self, planting_id: str) -> Planting:
        """A plan's seeds went in today: its dates now count from today."""
        planting = self._planting(planting_id)
        if not planting.planned:
            raise MicrogreensError("already_sown")
        today = self.today()
        candidate = replace(planting, planned=False, sown_on=today, last_watered_on=today)
        self._check_free(candidate, ignore=planting.id)
        self.data.plantings[self.data.plantings.index(planting)] = candidate
        self._changed()
        return candidate

    @callback
    def uncover(self, planting_id: str) -> Planting:
        planting = self._sown(planting_id)
        if planting.uncovered_on is None:
            planting.uncovered_on = self.today()
            self._changed()
        return planting

    @callback
    def water(self, planting_ids: Iterable[str] | None = None) -> int:
        """Mark plantings watered today. None waters every tray that is due."""
        today = self.today()
        if planting_ids is None:
            targets = [
                p for p in self.data.plantings if schedule.computed(p, today)["needs_water"]
            ]
        else:
            targets = [self._sown(pid) for pid in dict.fromkeys(planting_ids)]
        for planting in targets:
            planting.last_watered_on = today
        if targets:
            self._changed()
        return len(targets)

    @callback
    def shift(self, planting_id: str, days: Any) -> Planting:
        """Move a plan's sowing date, or a sown tray's harvest, by ``days``."""
        delta = clean_int(days, "days", -MAX_STAGE_DAYS, MAX_STAGE_DAYS)
        planting = self._planting(planting_id)
        if planting.planned:
            changes = {"sown_on": planting.sown_on + timedelta(days=delta)}
        else:
            light = planting.crop.light_days + delta
            if light < 1:
                raise MicrogreensError("shift_too_far")
            changes = {"light_days": light}
        return self.update_planting(planting_id, changes)

    @callback
    def harvest(
        self,
        planting_id: str,
        *,
        yield_grams: Any = None,
        rating: Any = None,
        notes: str = "",
        ended_on: Any = None,
    ) -> HistoryEntry:
        planting = self._sown(planting_id)
        entry = self._history_from(
            planting,
            OUTCOME_HARVESTED,
            self._end_date(planting, ended_on),
            yield_grams=clean_optional_float(yield_grams, "yield_grams", MAX_YIELD_G),
            rating=clean_rating(rating),
            notes=clean_text(notes),
        )
        self.data.plantings.remove(planting)
        self.data.history.append(entry)
        self._changed()
        return entry

    @callback
    def discard(self, planting_id: str, *, reason: str = "", notes: str = "") -> HistoryEntry | None:
        """A failed tray goes to history; a plan that never happened just goes."""
        planting = self._planting(planting_id)
        entry = None
        if not planting.planned:
            entry = self._history_from(
                planting,
                OUTCOME_DISCARDED,
                self.today(),
                reason=clean_reason(reason) or "other",
                notes=clean_text(notes),
            )
            self.data.history.append(entry)
        self.data.plantings.remove(planting)
        self._changed()
        return entry

    @callback
    def complete_task(self, task_id: str) -> None:
        """Do what a task asks (to-do list check-off): ``water:<id>`` etc."""
        kind, _, planting_id = task_id.partition(":")
        actions: dict[str, Callable[[str], Any]] = {
            TASK_WATER: lambda pid: self.water([pid]),
            TASK_UNCOVER: self.uncover,
            TASK_SOW: self.confirm_sown,
            TASK_SOAK: self.soak,
            TASK_HARVEST: self.harvest,
        }
        if kind not in actions:
            raise MicrogreensError("unknown_task")
        actions[kind](planting_id)

    # ------------------------------------------------------------------ #
    # History
    # ------------------------------------------------------------------ #

    @callback
    def update_history(self, entry_id: str, changes: Mapping[str, Any]) -> HistoryEntry:
        entry = self._history(entry_id)
        updated = replace(entry)
        if "yield_grams" in changes:
            updated.yield_grams = clean_optional_float(changes["yield_grams"], "yield_grams", MAX_YIELD_G)
        if "rating" in changes:
            updated.rating = clean_rating(changes["rating"])
        if "notes" in changes:
            updated.notes = clean_text(changes["notes"])
        if "reason" in changes and updated.outcome == OUTCOME_DISCARDED:
            updated.reason = clean_reason(changes["reason"]) or "other"
        if "ended_on" in changes:
            day = clean_date(changes["ended_on"], "ended_on")
            if day < updated.sown_on or day > self.today():
                raise MicrogreensError("invalid_date", field="ended_on")
            updated.ended_on = day
        self.data.history[self.data.history.index(entry)] = updated
        self._changed()
        return updated

    @callback
    def reopen_history(self, entry_id: str) -> Planting:
        """Undo a harvest or discard: the tray is back on its plot."""
        entry = self._history(entry_id)
        plot = self._plot(entry.plot_id)
        planting = Planting(
            id=new_id(),
            plot_id=plot.id,
            profile_id=entry.profile_id,
            crop=entry.crop,
            sown_on=entry.sown_on,
            label=entry.label,
            notes=entry.notes,
            uncovered_on=entry.uncovered_on,
            last_watered_on=min(entry.ended_on, self.today()),
        )
        self._check_free(planting)
        self.data.history.remove(entry)
        self.data.plantings.append(planting)
        self._changed()
        return planting

    @callback
    def delete_history(self, entry_id: str) -> None:
        self.data.history.remove(self._history(entry_id))
        self._changed()

    # ------------------------------------------------------------------ #
    # Backup
    # ------------------------------------------------------------------ #

    def export(self) -> dict[str, Any]:
        return {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "integration_version": self.version,
            "exported_at": dt_util.now().isoformat(),
            "data": {k: v for k, v in self.data.to_store().items() if k != "meta"},
        }

    @callback
    def import_backup(self, raw: Mapping[str, Any]) -> None:
        """Replace everything with a backup made by :meth:`export`."""
        if not isinstance(raw, Mapping) or raw.get("format") != BACKUP_FORMAT:
            raise MicrogreensError("invalid_backup")
        try:
            version = int(raw.get("version", 0))
        except (TypeError, ValueError):
            version = 0
        if version < 1 or version > BACKUP_VERSION:
            raise MicrogreensError("invalid_backup")
        data = GardenData.from_store(raw.get("data"))
        known = {p.id for p in data.plots}
        data.plantings = [p for p in data.plantings if p.plot_id in known]
        if len(data.plots) > MAX_PLOTS or len(data.profiles) > MAX_PROFILES:
            raise MicrogreensError("too_many", max=MAX_PLOTS)
        data.meta = dict(self.data.meta)
        self.data = data
        self._changed(plots=True)

    # ------------------------------------------------------------------ #
    # Notifications
    # ------------------------------------------------------------------ #

    async def async_send_digest(self, *, force: bool = False) -> bool:
        """The morning digest. Once per day unless ``force``; nothing if no tasks."""
        return await self._async_send_scheduled(KIND_DIGEST, "digest_sent_on", force)

    async def async_send_reminder(self, *, force: bool = False) -> bool:
        return await self._async_send_scheduled(KIND_REMINDER, "reminder_sent_on", force)

    async def _async_send_scheduled(self, kind: str, meta_key: str, force: bool) -> bool:
        today = self.today().isoformat()
        if not force and self.data.meta.get(meta_key) == today:
            return False
        self.data.meta[meta_key] = today
        self._store.async_delay_save(self.data.to_store, SAVE_DELAY_S)
        notice = build_notice(kind, self.tasks(), self._plantings_by_id(), self._plots_by_id(), self._strings)
        if notice is None:
            return False
        await self._async_deliver(notice)
        return True

    async def async_send_test(self) -> int:
        """A test notification to every target; returns how many it went to."""
        notice = Notice(
            kind=KIND_TEST,
            title=fmt(self._strings, "test_title"),
            message=fmt(self._strings, "test_message"),
        )
        return await self._async_deliver(notice)

    async def _async_deliver(self, notice: Notice) -> int:
        sent = 0
        if self.options[CONF_PERSISTENT] and notice.kind != KIND_TEST:
            persistent_notification.async_create(
                self.hass, notice.message, notice.title, PERSISTENT_NOTIFICATION_ID
            )
            self._persistent_tasks = notice.task_ids
        for target in self.options[CONF_NOTIFY_TARGETS]:
            if await self._async_send_to(target, notice):
                sent += 1
        return sent

    async def _async_send_to(self, target: str, notice: Notice) -> bool:
        domain, _, name = target.partition(".")
        try:
            if domain == "notify" and name and self.hass.services.has_service("notify", name):
                payload: dict[str, Any] = {"title": notice.title, "message": notice.message}
                if is_mobile_target(target):
                    payload["data"] = mobile_data(
                        notice,
                        entry_id=self.entry.entry_id,
                        url=f"/{PANEL_URL_PATH}",
                        strings=self._strings,
                        actions=self.options[CONF_ACTIONS],
                    )
                await self.hass.services.async_call("notify", name, payload, blocking=True)
                return True
            if domain == "notify" and self.hass.states.get(target) is not None:
                await self.hass.services.async_call(
                    "notify",
                    "send_message",
                    {"entity_id": target, "title": notice.title, "message": notice.message},
                    blocking=True,
                )
                return True
        except (HomeAssistantError, ValueError) as err:
            _LOGGER.warning("Could not send the Microgreens notification to %s: %s", target, err)
            return False
        if target not in self._warned_targets:
            self._warned_targets.add(target)
            _LOGGER.warning("Notification target %s does not exist; skipping it", target)
        return False

    @callback
    def _refresh_persistent(self) -> None:
        """Keep the sidebar notification in step with what is still open."""
        if self._persistent_tasks is None:
            return
        open_ids = {t.id for t in self.tasks()}
        remaining = tuple(t for t in self._persistent_tasks if t in open_ids)
        if remaining == self._persistent_tasks:
            return
        if not remaining:
            persistent_notification.async_dismiss(self.hass, PERSISTENT_NOTIFICATION_ID)
            self._persistent_tasks = None
            return
        tasks = [t for t in self.tasks() if t.id in remaining]
        notice = build_notice(KIND_DIGEST, tasks, self._plantings_by_id(), self._plots_by_id(), self._strings)
        if notice is not None:
            persistent_notification.async_create(
                self.hass, notice.message, notice.title, PERSISTENT_NOTIFICATION_ID
            )
        self._persistent_tasks = remaining

    @callback
    def _on_mobile_action(self, event: Event) -> None:
        if event.data.get("action") == water_all_action(self.entry.entry_id):
            count = self.water(None)
            _LOGGER.debug("Watered %d trays from a notification action", count)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _plantings_by_id(self) -> dict[str, Planting]:
        return {p.id: p for p in self.data.plantings}

    def _plots_by_id(self) -> dict[str, Plot]:
        return {p.id: p for p in self.data.plots}

    def _plot(self, plot_id: Any) -> Plot:
        plot = self.data.plot(str(plot_id or ""))
        if plot is None:
            raise MicrogreensError("unknown_plot", plot=plot_id)
        return plot

    def _profile(self, profile_id: Any) -> Profile:
        profile = self.data.profile(str(profile_id or ""))
        if profile is None:
            raise MicrogreensError("unknown_crop", crop=profile_id)
        return profile

    def _planting(self, planting_id: Any) -> Planting:
        planting = self.data.planting(str(planting_id or ""))
        if planting is None:
            raise MicrogreensError("unknown_planting")
        return planting

    def _sown(self, planting_id: Any) -> Planting:
        planting = self._planting(planting_id)
        if planting.planned:
            raise MicrogreensError("not_sown")
        return planting

    def _history(self, entry_id: Any) -> HistoryEntry:
        entry = self.data.history_entry(str(entry_id or ""))
        if entry is None:
            raise MicrogreensError("unknown_history")
        return entry

    def _check_free(self, planting: Planting, ignore: str | None = None) -> None:
        today = self.today()
        for other in self.data.plantings:
            if other.id in (planting.id, ignore) or other.plot_id != planting.plot_id:
                continue
            if schedule.overlaps(planting, other, today):
                raise MicrogreensError(
                    "plot_busy",
                    plot=self._plot(planting.plot_id).name,
                    crop=other.crop.name,
                    start=other.sown_on.isoformat(),
                    end=schedule.occupancy_end(other, today).isoformat(),
                )

    def _end_date(self, planting: Planting, value: Any) -> date:
        today = self.today()
        if not value:
            return today
        day = clean_date(value, "ended_on")
        if day < planting.sown_on or day > today:
            raise MicrogreensError("invalid_date", field="ended_on")
        return day

    def _history_from(self, planting: Planting, outcome: str, ended_on: date, **extra: Any) -> HistoryEntry:
        plot = self.data.plot(planting.plot_id)
        notes = extra.pop("notes", "")
        combined = "\n".join(n for n in (planting.notes, notes) if n)
        return HistoryEntry(
            id=planting.id,
            plot_id=planting.plot_id,
            plot_name=plot.name if plot else planting.plot_id,
            profile_id=planting.profile_id,
            crop=planting.crop,
            sown_on=planting.sown_on,
            ended_on=ended_on,
            outcome=outcome,
            label=planting.label,
            notes=combined[:MAX_NOTES_LEN],
            uncovered_on=planting.uncovered_on,
            **extra,
        )
