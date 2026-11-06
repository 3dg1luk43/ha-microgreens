# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Data model and write validation. Pure: imports nothing from Home Assistant.

Two ways in, deliberately different:

* ``*.from_store`` is tolerant. It reads what is on disk (or a backup) and fills
  anything missing with a default, because refusing to load means losing a
  user's whole garden over one bad field.
* ``clean_*`` is strict. Every write from the panel, a service or an import goes
  through it and raises :class:`MicrogreensError`, whose ``key`` is a
  translation key under ``exceptions`` in strings.json.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from typing import Any

from .const import (
    DISCARD_REASONS,
    MAX_NAME_LEN,
    MAX_NOTES_LEN,
    MAX_SOAK_HOURS,
    MAX_STAGE_DAYS,
    MAX_WATER_DAYS,
    MAX_WINDOW_DAYS,
    MAX_YIELD_G,
    OUTCOME_DISCARDED,
    OUTCOME_HARVESTED,
    PROFILE_PALETTE,
)

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


class MicrogreensError(Exception):
    """A refused write. ``key`` is a strings.json ``exceptions`` key."""

    def __init__(self, key: str, **placeholders: Any) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = {k: str(v) for k, v in placeholders.items()}


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


@dataclass
class Profile:
    """A crop: how long each stage takes and how often it is watered."""

    id: str
    name: str
    color: str
    soak_hours: int = 0
    cover_days: int = 3
    light_days: int = 7
    harvest_window_days: int = 3
    water_every_days: int = 1
    seed_grams: float | None = None
    notes: str = ""

    @property
    def total_days(self) -> int:
        return self.cover_days + self.light_days

    @classmethod
    def from_store(cls, raw: Mapping[str, Any], index: int = 0) -> Profile:
        return cls(
            id=str(raw.get("id") or f"crop_{index}"),
            name=str(raw.get("name") or raw.get("id") or f"Crop {index + 1}"),
            color=_color_or(raw.get("color"), index),
            soak_hours=_int_or(raw.get("soak_hours"), 0),
            cover_days=_int_or(raw.get("cover_days"), 3),
            light_days=_int_or(raw.get("light_days"), 7),
            harvest_window_days=max(1, _int_or(raw.get("harvest_window_days"), 3)),
            water_every_days=_int_or(raw.get("water_every_days"), 1),
            seed_grams=_float_or_none(raw.get("seed_grams")),
            notes=str(raw.get("notes") or ""),
        )


@dataclass
class Plot:
    """A tray position. ``id`` is immutable (entity unique ids use it)."""

    id: str
    name: str
    location: str = ""
    order: int = 0

    @classmethod
    def from_store(cls, raw: Mapping[str, Any], index: int = 0) -> Plot:
        pid = str(raw.get("id") or f"P{index + 1}")
        return cls(
            id=pid,
            name=str(raw.get("name") or pid),
            location=str(raw.get("location") or ""),
            order=_int_or(raw.get("order"), index),
        )


@dataclass
class Crop:
    """The profile's numbers as they were when the tray was sown.

    A snapshot, so editing a profile never moves the dates of trays already
    growing; a planting's own numbers are edited on the planting.
    """

    name: str
    color: str
    soak_hours: int = 0
    cover_days: int = 3
    light_days: int = 7
    harvest_window_days: int = 3
    water_every_days: int = 1

    @classmethod
    def from_profile(cls, profile: Profile) -> Crop:
        return cls(
            name=profile.name,
            color=profile.color,
            soak_hours=profile.soak_hours,
            cover_days=profile.cover_days,
            light_days=profile.light_days,
            harvest_window_days=profile.harvest_window_days,
            water_every_days=profile.water_every_days,
        )

    @classmethod
    def from_store(cls, raw: Mapping[str, Any] | None) -> Crop:
        raw = raw or {}
        return cls(
            name=str(raw.get("name") or "?"),
            color=_color_or(raw.get("color"), 0),
            soak_hours=_int_or(raw.get("soak_hours"), 0),
            cover_days=_int_or(raw.get("cover_days"), 3),
            light_days=_int_or(raw.get("light_days"), 7),
            harvest_window_days=max(1, _int_or(raw.get("harvest_window_days"), 3)),
            water_every_days=_int_or(raw.get("water_every_days"), 1),
        )


@dataclass
class Planting:
    """One tray of one crop on one plot, from plan to harvest."""

    id: str
    plot_id: str
    profile_id: str
    crop: Crop
    sown_on: date
    # True until the user confirms the seeds are in. A planting created for
    # today or earlier is sown; one created for a later date is a plan.
    planned: bool = False
    label: str = ""
    notes: str = ""
    soaked_on: date | None = None
    uncovered_on: date | None = None
    last_watered_on: date | None = None

    @classmethod
    def from_store(cls, raw: Mapping[str, Any]) -> Planting:
        sown = _date_or_none(raw.get("sown_on"))
        if sown is None:
            raise ValueError("planting without sown_on")
        return cls(
            id=str(raw.get("id") or new_id()),
            plot_id=str(raw["plot_id"]),
            profile_id=str(raw.get("profile_id") or ""),
            crop=Crop.from_store(raw.get("crop")),
            sown_on=sown,
            planned=bool(raw.get("planned", False)),
            label=str(raw.get("label") or ""),
            notes=str(raw.get("notes") or ""),
            soaked_on=_date_or_none(raw.get("soaked_on")),
            uncovered_on=_date_or_none(raw.get("uncovered_on")),
            last_watered_on=_date_or_none(raw.get("last_watered_on")),
        )


@dataclass
class HistoryEntry:
    """A finished planting: harvested or discarded."""

    id: str
    plot_id: str
    plot_name: str
    profile_id: str
    crop: Crop
    sown_on: date
    ended_on: date
    outcome: str = OUTCOME_HARVESTED
    yield_grams: float | None = None
    rating: int | None = None
    reason: str = ""
    label: str = ""
    notes: str = ""
    uncovered_on: date | None = None

    @classmethod
    def from_store(cls, raw: Mapping[str, Any]) -> HistoryEntry:
        sown = _date_or_none(raw.get("sown_on"))
        ended = _date_or_none(raw.get("ended_on"))
        if sown is None or ended is None:
            raise ValueError("history entry without dates")
        outcome = raw.get("outcome")
        rating = _int_or(raw.get("rating"), 0)
        return cls(
            id=str(raw.get("id") or new_id()),
            plot_id=str(raw.get("plot_id") or ""),
            plot_name=str(raw.get("plot_name") or raw.get("plot_id") or ""),
            profile_id=str(raw.get("profile_id") or ""),
            crop=Crop.from_store(raw.get("crop")),
            sown_on=sown,
            ended_on=ended,
            outcome=outcome if outcome in (OUTCOME_HARVESTED, OUTCOME_DISCARDED) else OUTCOME_HARVESTED,
            yield_grams=_float_or_none(raw.get("yield_grams")),
            rating=rating if 1 <= rating <= 5 else None,
            reason=str(raw.get("reason") or ""),
            label=str(raw.get("label") or ""),
            notes=str(raw.get("notes") or ""),
            uncovered_on=_date_or_none(raw.get("uncovered_on")),
        )


@dataclass
class GardenData:
    """Everything the integration stores."""

    plots: list[Plot] = field(default_factory=list)
    profiles: list[Profile] = field(default_factory=list)
    plantings: list[Planting] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    # Bookkeeping that must survive a restart (notification de-duplication).
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_store(cls, raw: Mapping[str, Any] | None) -> GardenData:
        """Load stored data, dropping only the records that cannot be read."""
        raw = raw or {}
        data = cls(meta=dict(raw.get("meta") or {}))
        seen: set[str] = set()
        for i, item in enumerate(_rows(raw.get("plots"))):
            plot = Plot.from_store(item, i)
            if plot.id not in seen:
                seen.add(plot.id)
                data.plots.append(plot)
        seen = set()
        for i, item in enumerate(_rows(raw.get("profiles"))):
            prof = Profile.from_store(item, i)
            if prof.id not in seen:
                seen.add(prof.id)
                data.profiles.append(prof)
        for item in _rows(raw.get("plantings")):
            try:
                data.plantings.append(Planting.from_store(item))
            except (KeyError, TypeError, ValueError):
                continue
        for item in _rows(raw.get("history")):
            try:
                data.history.append(HistoryEntry.from_store(item))
            except (KeyError, TypeError, ValueError):
                continue
        data.plots.sort(key=lambda p: p.order)
        return data

    def to_store(self) -> dict[str, Any]:
        return {
            "plots": [asdict(p) for p in self.plots],
            "profiles": [asdict(p) for p in self.profiles],
            "plantings": [to_jsonable(asdict(p)) for p in self.plantings],
            "history": [to_jsonable(asdict(h)) for h in self.history],
            "meta": dict(self.meta),
        }

    # lookups
    def plot(self, plot_id: str) -> Plot | None:
        return next((p for p in self.plots if p.id == plot_id), None)

    def profile(self, profile_id: str) -> Profile | None:
        return next((p for p in self.profiles if p.id == profile_id), None)

    def planting(self, planting_id: str) -> Planting | None:
        return next((p for p in self.plantings if p.id == planting_id), None)

    def history_entry(self, entry_id: str) -> HistoryEntry | None:
        return next((h for h in self.history if h.id == entry_id), None)


# --------------------------------------------------------------------------- #
# Strict write validation
# --------------------------------------------------------------------------- #


def clean_name(value: Any, field_name: str = "name") -> str:
    text = str(value or "").strip()
    if not text or len(text) > MAX_NAME_LEN:
        raise MicrogreensError("invalid_name", field=field_name, max=MAX_NAME_LEN)
    return text


def clean_text(value: Any, max_len: int = MAX_NOTES_LEN) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        raise MicrogreensError("text_too_long", max=max_len)
    return text


def clean_int(value: Any, field_name: str, lo: int, hi: int) -> int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MicrogreensError("invalid_number", field=field_name, min=lo, max=hi) from None
    if number != int(number) or not lo <= number <= hi:
        raise MicrogreensError("invalid_number", field=field_name, min=lo, max=hi)
    return int(number)


def clean_optional_float(value: Any, field_name: str, hi: float) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise MicrogreensError("invalid_number", field=field_name, min=0, max=hi) from None
    if number != number or not 0 <= number <= hi:  # NaN fails the first test
        raise MicrogreensError("invalid_number", field=field_name, min=0, max=hi)
    return round(number, 1)


def clean_date(value: Any, field_name: str = "date") -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise MicrogreensError("invalid_date", field=field_name) from None


def clean_color(value: Any, index: int) -> str:
    if value in (None, ""):
        return PROFILE_PALETTE[index % len(PROFILE_PALETTE)]
    text = str(value).strip()
    if not _COLOR_RE.match(text):
        raise MicrogreensError("invalid_color")
    return text.lower()


def clean_id(value: Any) -> str:
    text = str(value or "").strip()
    if not _ID_RE.match(text):
        raise MicrogreensError("invalid_id")
    return text


def clean_stage_numbers(raw: Mapping[str, Any], base: Crop | Profile) -> dict[str, int]:
    """Validate the stage fields present in ``raw``; absent ones keep ``base``'s."""
    out = {
        "soak_hours": base.soak_hours,
        "cover_days": base.cover_days,
        "light_days": base.light_days,
        "harvest_window_days": base.harvest_window_days,
        "water_every_days": base.water_every_days,
    }
    limits = {
        "soak_hours": (0, MAX_SOAK_HOURS),
        "cover_days": (0, MAX_STAGE_DAYS),
        "light_days": (1, MAX_STAGE_DAYS),
        "harvest_window_days": (1, MAX_WINDOW_DAYS),
        "water_every_days": (0, MAX_WATER_DAYS),
    }
    for key, (lo, hi) in limits.items():
        if key in raw and raw[key] is not None:
            out[key] = clean_int(raw[key], key, lo, hi)
    return out


def clean_profile(raw: Mapping[str, Any], existing: Iterable[Profile]) -> Profile:
    """A profile to create (no/unknown ``id``) or replace (known ``id``)."""
    existing = list(existing)
    current = next((p for p in existing if p.id == raw.get("id")), None) if raw.get("id") else None
    name = clean_name(raw.get("name"))
    if current is None:
        pid = unique_slug(raw.get("id") or name, {p.id for p in existing}, "crop")
        base = Profile(id=pid, name=name, color=PROFILE_PALETTE[len(existing) % len(PROFILE_PALETTE)])
        index = len(existing)
    else:
        base = current
        index = existing.index(current)
    numbers = clean_stage_numbers(raw, base)
    return Profile(
        id=base.id,
        name=name,
        color=clean_color(raw.get("color", base.color), index),
        seed_grams=clean_optional_float(raw.get("seed_grams", base.seed_grams), "seed_grams", MAX_YIELD_G),
        notes=clean_text(raw.get("notes", base.notes)),
        **numbers,
    )


def clean_plot(raw: Mapping[str, Any], existing: Iterable[Plot]) -> tuple[Plot, bool]:
    """A plot to create or rename. Returns ``(plot, created)``."""
    existing = list(existing)
    current = next((p for p in existing if p.id == raw.get("id")), None) if raw.get("id") else None
    name = clean_name(raw.get("name") or raw.get("id"))
    location = clean_text(raw.get("location", current.location if current else ""), MAX_NAME_LEN)
    if current is not None:
        return replace(current, name=name, location=location), False
    if raw.get("id"):
        pid = clean_id(raw["id"])
    else:
        pid = unique_slug(name, {p.id for p in existing}, "plot")
    if any(p.id.lower() == pid.lower() for p in existing):
        raise MicrogreensError("plot_exists", plot=pid)
    order = max((p.order for p in existing), default=-1) + 1
    return Plot(id=pid, name=name, location=location, order=order), True


def clean_rating(value: Any) -> int | None:
    if value in (None, "", 0):
        return None
    return clean_int(value, "rating", 1, 5)


def clean_reason(value: Any) -> str:
    text = str(value or "").strip()
    if text and text not in DISCARD_REASONS:
        raise MicrogreensError("invalid_reason")
    return text


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def slugify(text: Any, fallback: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", folded.lower()).strip("_")[:24]
    return slug or fallback


def unique_slug(text: Any, taken: set[str], fallback: str) -> str:
    base = slugify(text, fallback)
    lowered = {t.lower() for t in taken}
    candidate, n = base, 2
    while candidate.lower() in lowered:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


def to_jsonable(value: Any) -> Any:
    """Dates to ISO strings, recursively (``asdict`` keeps them as dates)."""
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, Mapping)]


def _int_or(value: Any, default: int) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _float_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number >= 0 else None


def _date_or_none(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _color_or(value: Any, index: int) -> str:
    if isinstance(value, str) and _COLOR_RE.match(value):
        return value.lower()
    return PROFILE_PALETTE[index % len(PROFILE_PALETTE)]


# --------------------------------------------------------------------------- #
# 0.1.x import
# --------------------------------------------------------------------------- #


def migrate_legacy(raw: Mapping[str, Any] | None, today: date) -> GardenData:
    """Convert a 0.1.x ``microgreens`` store into :class:`GardenData`.

    0.1.x stored ``{plots: [{id, label}], profiles: [{id, name, cover_days,
    uncover_days, watering_frequency_days, notes}], deployments: [{plot_id,
    sticker, plant_id, plant_name, start_date, cover_end, harvest_date,
    watering_every_days, next_watering_due, notes}]}``. A row that cannot be
    read is skipped, never the whole store.

    A deployment whose ``cover_end`` has passed is taken as uncovered on that
    day: 0.1.x had no way to record it, and assuming otherwise would greet every
    upgraded user with an overdue "uncover" task per tray.
    """
    raw = raw or {}
    data = GardenData(meta={"legacy_imported_on": today.isoformat()})
    for i, row in enumerate(_rows(raw.get("plots"))):
        pid = str(row.get("id") or "").strip()
        if not _ID_RE.match(pid) or data.plot(pid):
            continue
        data.plots.append(Plot(id=pid, name=str(row.get("label") or pid)[:MAX_NAME_LEN], order=i))
    for i, row in enumerate(_rows(raw.get("profiles"))):
        prid = str(row.get("id") or "").strip()
        if not prid or data.profile(prid):
            continue
        data.profiles.append(
            Profile(
                id=prid,
                name=str(row.get("name") or prid)[:MAX_NAME_LEN],
                color=PROFILE_PALETTE[i % len(PROFILE_PALETTE)],
                cover_days=min(_int_or(row.get("cover_days"), 3), MAX_STAGE_DAYS),
                light_days=min(max(1, _int_or(row.get("uncover_days"), 7)), MAX_STAGE_DAYS),
                harvest_window_days=2,
                water_every_days=min(_int_or(row.get("watering_frequency_days"), 1), MAX_WATER_DAYS),
                notes=str(row.get("notes") or "")[:MAX_NOTES_LEN],
            )
        )
    colors = {p.id: p.color for p in data.profiles}
    for row in _rows(raw.get("deployments")):
        start = _date_or_none(row.get("start_date"))
        plot_id = str(row.get("plot_id") or "")
        if start is None or not data.plot(plot_id):
            continue
        if any(p.plot_id == plot_id for p in data.plantings):
            continue  # 0.1.x allowed one per plot; keep the first
        cover_end = _date_or_none(row.get("cover_end")) or start
        harvest = _date_or_none(row.get("harvest_date")) or cover_end
        cover_days = max(0, (cover_end - start).days)
        light_days = max(1, (harvest - cover_end).days)
        every = _int_or(row.get("watering_every_days"), 1)
        next_due = _date_or_none(row.get("next_watering_due"))
        last_watered = start
        if next_due is not None and every > 0:
            last_watered = max(start, date.fromordinal(next_due.toordinal() - every))
        profile_id = str(row.get("plant_id") or "")
        data.plantings.append(
            Planting(
                id=new_id(),
                plot_id=plot_id,
                profile_id=profile_id,
                crop=Crop(
                    name=str(row.get("plant_name") or profile_id or "?")[:MAX_NAME_LEN],
                    color=colors.get(profile_id, PROFILE_PALETTE[0]),
                    cover_days=min(cover_days, MAX_STAGE_DAYS),
                    light_days=min(light_days, MAX_STAGE_DAYS),
                    harvest_window_days=2,
                    water_every_days=min(every, MAX_WATER_DAYS),
                ),
                sown_on=start,
                planned=start > today,
                label=str(row.get("sticker") or "")[:MAX_NAME_LEN],
                notes=str(row.get("notes") or "")[:MAX_NOTES_LEN],
                uncovered_on=cover_end if cover_days and cover_end <= today and start <= today else None,
                last_watered_on=min(last_watered, today) if start <= today else None,
            )
        )
    return data
