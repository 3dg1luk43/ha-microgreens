# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Grow-schedule maths: dates, status, occupancy and today's tasks.

The single source of truth. Entities, the panel, the card, the to-do list and
the notifications all read these functions (the frontend gets the results in
the WebSocket snapshot); none of them re-derives a status or a date. Pure: no
Home Assistant, and "today" is always passed in (the caller uses HA's time
zone, never the host's).

Stage model, for a planting sown on day S with crop numbers cover/light/window:

    S ............ S+cover ............ S+cover+light ..... +window-1
    | covered      | growing (light)    | ready (harvest window) | overdue

A planned planting (seeds not in yet) is ``planned`` until the user confirms
sowing. Uncovering is a recorded event: a tray stays ``covered`` past its
uncover date until someone uncovers it (an open, late task), but the harvest
dates do not move with it; the window is anchored to the sowing date.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import Any

from .const import (
    GROWING_STATUSES,
    STATUS_COVERED,
    STATUS_EMPTY,
    STATUS_GROWING,
    STATUS_OVERDUE,
    STATUS_PLANNED,
    STATUS_READY,
    TASK_HARVEST,
    TASK_ORDER,
    TASK_SOAK,
    TASK_SOW,
    TASK_UNCOVER,
    TASK_WATER,
)
from .models import Planting, Plot


@dataclass(frozen=True)
class Times:
    """A planting's planned dates."""

    soak_on: date | None
    sown_on: date
    uncover_on: date
    harvest_start: date
    harvest_end: date

    @property
    def total_days(self) -> int:
        return (self.harvest_start - self.sown_on).days


def times(p: Planting) -> Times:
    crop = p.crop
    soak_on = None
    if crop.soak_hours > 0:
        soak_on = p.sown_on - timedelta(days=max(1, ceil(crop.soak_hours / 24)))
    uncover_on = p.sown_on + timedelta(days=crop.cover_days)
    harvest_start = uncover_on + timedelta(days=crop.light_days)
    harvest_end = harvest_start + timedelta(days=max(1, crop.harvest_window_days) - 1)
    return Times(soak_on, p.sown_on, uncover_on, harvest_start, harvest_end)


def status(p: Planting, today: date) -> str:
    if p.planned:
        return STATUS_PLANNED
    t = times(p)
    if today > t.harvest_end:
        return STATUS_OVERDUE
    if today >= t.harvest_start:
        return STATUS_READY
    if p.crop.cover_days > 0 and p.uncovered_on is None:
        return STATUS_COVERED
    return STATUS_GROWING


def water_due_on(p: Planting) -> date | None:
    """When the tray next needs water, or None if it is not watered on a schedule."""
    if p.planned or p.crop.water_every_days <= 0:
        return None
    last = p.last_watered_on or p.sown_on
    return last + timedelta(days=p.crop.water_every_days)


def occupancy_end(p: Planting, today: date) -> date:
    """Last day the planting holds its plot. A late harvest holds it until today."""
    end = times(p).harvest_end
    if not p.planned and today > end:
        return today
    return end


def overlaps(a: Planting, b: Planting, today: date) -> bool:
    """True when two plantings want the same plot at the same time.

    Same-day turnover is allowed: harvesting in the morning and sowing the next
    tray that evening is normal, so a planting may start on the day the other
    one's window ends.
    """
    return a.sown_on < occupancy_end(b, today) and b.sown_on < occupancy_end(a, today)


def current_for_plot(plantings: Iterable[Planting], plot_id: str) -> tuple[Planting | None, Planting | None]:
    """``(current, next_planned)`` for one plot.

    Current is the sown planting if there is one, else the earliest plan;
    next is the earliest plan after the current one.
    """
    mine = sorted((p for p in plantings if p.plot_id == plot_id), key=lambda p: p.sown_on)
    sown = [p for p in mine if not p.planned]
    plans = [p for p in mine if p.planned]
    if sown:
        return sown[0], plans[0] if plans else None
    if plans:
        return plans[0], plans[1] if len(plans) > 1 else None
    return None, None


def plot_status(plantings: Iterable[Planting], plot_id: str, today: date) -> str:
    current, _ = current_for_plot(plantings, plot_id)
    return status(current, today) if current else STATUS_EMPTY


def progress(p: Planting, today: date) -> float:
    """0..1 through the grow (sowing to the start of the harvest window)."""
    if p.planned:
        return 0.0
    t = times(p)
    total = max(1, t.total_days)
    return max(0.0, min(1.0, (today - t.sown_on).days / total))


def computed(p: Planting, today: date) -> dict[str, Any]:
    """Everything derived about a planting, JSON-ready (the snapshot's ``computed``)."""
    t = times(p)
    due = water_due_on(p)
    st = status(p, today)
    return {
        "status": st,
        "soak_on": t.soak_on.isoformat() if t.soak_on else None,
        "uncover_on": t.uncover_on.isoformat(),
        "harvest_start": t.harvest_start.isoformat(),
        "harvest_end": t.harvest_end.isoformat(),
        "total_days": t.total_days,
        # Day 1 is the sowing day; 0 while still planned.
        "day": 0 if p.planned else max(0, (today - p.sown_on).days + 1),
        "progress": round(progress(p, today), 3),
        "water_due_on": due.isoformat() if due else None,
        "needs_water": bool(due and due <= today and st in GROWING_STATUSES),
        "days_to_harvest": (t.harvest_start - today).days,
    }


@dataclass(frozen=True)
class Task:
    """One thing to do. ``id`` is stable for as long as the task is open."""

    kind: str
    planting_id: str
    plot_id: str
    due_on: date
    late: bool = False
    # Harvest only: today is the last day of the window.
    last_day: bool = False

    @property
    def id(self) -> str:
        return f"{self.kind}:{self.planting_id}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "planting_id": self.planting_id,
            "plot_id": self.plot_id,
            "due_on": self.due_on.isoformat(),
            "late": self.late,
            "last_day": self.last_day,
        }


def tasks_for_planting(p: Planting, today: date) -> list[Task]:
    t = times(p)
    out: list[Task] = []
    if p.planned:
        if t.soak_on is not None and p.soaked_on is None and today >= t.soak_on:
            out.append(Task(TASK_SOAK, p.id, p.plot_id, t.soak_on, late=today > t.soak_on))
        if today >= p.sown_on:
            out.append(Task(TASK_SOW, p.id, p.plot_id, p.sown_on, late=today > p.sown_on))
        return out
    st = status(p, today)
    if st in (STATUS_READY, STATUS_OVERDUE):
        out.append(
            Task(
                TASK_HARVEST,
                p.id,
                p.plot_id,
                t.harvest_start,
                late=st == STATUS_OVERDUE,
                last_day=today == t.harvest_end,
            )
        )
    elif st == STATUS_COVERED and today >= t.uncover_on:
        out.append(Task(TASK_UNCOVER, p.id, p.plot_id, t.uncover_on, late=today > t.uncover_on))
    due = water_due_on(p)
    if due is not None and due <= today and st in GROWING_STATUSES:
        out.append(Task(TASK_WATER, p.id, p.plot_id, due, late=today > due))
    return out


def tasks(plantings: Iterable[Planting], plots: Iterable[Plot], today: date) -> list[Task]:
    """Every open task today, in display order (kind, then plot order)."""
    order = {p.id: i for i, p in enumerate(sorted(plots, key=lambda p: p.order))}
    rank = {k: i for i, k in enumerate(TASK_ORDER)}
    out = [task for p in plantings for task in tasks_for_planting(p, today)]
    out.sort(key=lambda t: (rank.get(t.kind, 99), order.get(t.plot_id, 1 << 20), t.due_on))
    return out


def reminder_worthy(task: Task) -> bool:
    """Whether an evening reminder should nag about this task.

    A harvest window is several days long, so an open harvest is only worth a
    reminder on its last day or once it is late. Everything else that is still
    open in the evening is.
    """
    if task.kind == TASK_HARVEST:
        return task.last_day or task.late
    return True


def group_by_kind(items: Iterable[Task]) -> Mapping[str, list[Task]]:
    grouped: dict[str, list[Task]] = {}
    for task in items:
        grouped.setdefault(task.kind, []).append(task)
    return {k: grouped[k] for k in TASK_ORDER if k in grouped}
