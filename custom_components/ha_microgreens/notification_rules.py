# Microgreens - Home Assistant integration for planning and tracking microgreen trays.
# Copyright (C) 2026 Lukas Bandura
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Option coercion and notification content. Pure: imports nothing from HA.

No user-visible text lives here. Every word comes from strings.json ``common``
and is passed in already resolved (``strings``), with English merged under the
user's language so a key missing from a translation still reads.
Delivery (service calls, the persistent notification) is in ``manager.py``.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .const import (
    ACTION_WATER_ALL,
    CONF_ACTIONS,
    CONF_DIGEST_ENABLED,
    CONF_DIGEST_TIME,
    CONF_NOTIFY_TARGETS,
    CONF_PERSISTENT,
    CONF_REMINDER_ENABLED,
    CONF_REMINDER_TIME,
    DEFAULT_OPTIONS,
    DOMAIN,
    TASK_HARVEST,
    TASK_WATER,
)
from .models import Planting, Plot
from .schedule import Task, group_by_kind, reminder_worthy

KIND_DIGEST = "digest"
KIND_REMINDER = "reminder"
KIND_TEST = "test"

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")


# --------------------------------------------------------------------------- #
# Options
# --------------------------------------------------------------------------- #


def parse_time(value: Any, default: str) -> tuple[int, int, int]:
    """``"HH:MM[:SS]"`` to a tuple; anything unreadable falls back to ``default``."""
    for candidate in (value, default):
        m = _TIME_RE.match(str(candidate or "").strip())
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            if h < 24 and mi < 60 and s < 60:
                return h, mi, s
    return 8, 0, 0


def format_time(value: Any, default: str) -> str:
    h, m, s = parse_time(value, default)
    return f"{h:02d}:{m:02d}:{s:02d}"


def normalize_options(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """Every option present, typed, and in range."""
    raw = raw or {}
    out = dict(DEFAULT_OPTIONS)
    targets = raw.get(CONF_NOTIFY_TARGETS, out[CONF_NOTIFY_TARGETS])
    if isinstance(targets, str):
        targets = [t.strip() for t in targets.split(",")]
    out[CONF_NOTIFY_TARGETS] = list(
        dict.fromkeys(str(t).strip() for t in (targets or []) if str(t).strip().startswith("notify."))
    )
    for key in (CONF_PERSISTENT, CONF_DIGEST_ENABLED, CONF_REMINDER_ENABLED, CONF_ACTIONS):
        if key in raw:
            out[key] = bool(raw[key])
    out[CONF_DIGEST_TIME] = format_time(raw.get(CONF_DIGEST_TIME), DEFAULT_OPTIONS[CONF_DIGEST_TIME])
    out[CONF_REMINDER_TIME] = format_time(raw.get(CONF_REMINDER_TIME), DEFAULT_OPTIONS[CONF_REMINDER_TIME])
    return out


def legacy_options(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """0.1.x entry options (notify_service, summary_time, ...) to this release's."""
    raw = raw or {}
    out: dict[str, Any] = {}
    service = str(raw.get("notify_service") or "").strip()
    if service.startswith("notify.") and service != "notify.":
        out[CONF_NOTIFY_TARGETS] = [service]
    if raw.get("summary_time"):
        out[CONF_DIGEST_TIME] = raw["summary_time"]
    return normalize_options(out)


# --------------------------------------------------------------------------- #
# Content
# --------------------------------------------------------------------------- #


@dataclass
class Notice:
    """One notification, ready to deliver."""

    kind: str
    title: str
    message: str
    task_ids: tuple[str, ...] = ()
    water_count: int = 0
    lines: list[str] = field(default_factory=list)


def fmt(strings: Mapping[str, str], key: str, **values: Any) -> str:
    """Resolve ``key`` and fill its placeholders. Never raises.

    A translation with a broken placeholder yields its raw text rather than an
    exception in the middle of a delivery.
    """
    template = strings.get(key, key)
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def task_item(
    task: Task,
    plantings: Mapping[str, Planting],
    plots: Mapping[str, Plot],
    strings: Mapping[str, str],
) -> str:
    """``A1 (Radish)``, with ``, last day`` / ``, late`` where it matters."""
    planting = plantings.get(task.planting_id)
    plot = plots.get(task.plot_id)
    item = fmt(
        strings,
        "item",
        plot=plot.name if plot else task.plot_id,
        crop=planting.crop.name if planting else "?",
    )
    if task.kind == TASK_HARVEST and task.last_day:
        return fmt(strings, "tag_last_day", item=item)
    if task.late:
        return fmt(strings, "tag_late", item=item)
    return item


def task_summary(
    task: Task,
    plantings: Mapping[str, Planting],
    plots: Mapping[str, Plot],
    strings: Mapping[str, str],
) -> str:
    """One task as a sentence (to-do list items): ``Water A1 (Radish)``."""
    planting = plantings.get(task.planting_id)
    plot = plots.get(task.plot_id)
    return fmt(
        strings,
        f"task_{task.kind}",
        plot=plot.name if plot else task.plot_id,
        crop=planting.crop.name if planting else "?",
    )


def build_notice(
    kind: str,
    tasks: Iterable[Task],
    plantings: Mapping[str, Planting],
    plots: Mapping[str, Plot],
    strings: Mapping[str, str],
) -> Notice | None:
    """The digest or the reminder for ``tasks``; None when there is nothing to say."""
    chosen = [t for t in tasks if kind != KIND_REMINDER or reminder_worthy(t)]
    if not chosen:
        return None
    lines = []
    for task_kind, group in group_by_kind(chosen).items():
        items = ", ".join(task_item(t, plantings, plots, strings) for t in group)
        lines.append(fmt(strings, f"line_{task_kind}", items=items))
    return Notice(
        kind=kind,
        title=fmt(strings, f"{kind}_title"),
        message="\n".join(lines),
        task_ids=tuple(t.id for t in chosen),
        water_count=sum(1 for t in chosen if t.kind == TASK_WATER),
        lines=lines,
    )


def is_mobile_target(target: str) -> bool:
    """Companion-app targets get tags, a tap URL and action buttons."""
    return target.startswith("notify.mobile_app_")


def water_all_action(entry_id: str) -> str:
    return f"{ACTION_WATER_ALL}_{entry_id}"


def mobile_data(
    notice: Notice,
    *,
    entry_id: str,
    url: str,
    strings: Mapping[str, str],
    actions: bool,
) -> dict[str, Any]:
    """The companion app's ``data`` block for one notice.

    The tag is shared by the digest and the reminder, so the reminder replaces
    a digest still sitting on the phone instead of stacking a second one.
    """
    data: dict[str, Any] = {
        "tag": f"{DOMAIN}_tasks",
        "group": DOMAIN,
        "url": url,
        "clickAction": url,
    }
    if actions and notice.kind != KIND_TEST:
        buttons = []
        if notice.water_count:
            buttons.append({"action": water_all_action(entry_id), "title": fmt(strings, "action_water_all")})
        buttons.append({"action": "URI", "title": fmt(strings, "action_open"), "uri": url})
        data["actions"] = buttons
    return data
