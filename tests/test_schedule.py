"""Grow-schedule maths (schedule.py). Pure: no Home Assistant."""
from __future__ import annotations

from datetime import date, timedelta

from custom_components.ha_microgreens import schedule
from custom_components.ha_microgreens.models import Crop, Planting, Plot

D = date(2026, 10, 1)


def planting(**kw) -> Planting:
    crop = kw.pop("crop", None) or Crop(name="Radish", color="#e53935", cover_days=3, light_days=5, harvest_window_days=3, water_every_days=1)
    base = dict(id="p1", plot_id="A1", profile_id="radish", crop=crop, sown_on=D, last_watered_on=D)
    base.update(kw)
    return Planting(**base)


def day(n: int) -> date:
    return D + timedelta(days=n)


def test_times_follow_the_stage_lengths() -> None:
    t = schedule.times(planting())
    assert t.uncover_on == day(3)
    assert t.harvest_start == day(8)
    assert t.harvest_end == day(10)  # window of 3 days: 8, 9, 10
    assert t.total_days == 8
    assert t.soak_on is None


def test_soak_is_the_day_before_or_more_for_long_soaks() -> None:
    p = planting(crop=Crop(name="Pea", color="#43a047", soak_hours=12))
    assert schedule.times(p).soak_on == day(-1)
    p = planting(crop=Crop(name="Pea", color="#43a047", soak_hours=36))
    assert schedule.times(p).soak_on == day(-2)


def test_status_walks_through_the_stages() -> None:
    p = planting()
    assert schedule.status(p, day(0)) == "covered"
    assert schedule.status(p, day(5)) == "covered"  # not uncovered yet: stays covered
    p.uncovered_on = day(3)
    assert schedule.status(p, day(5)) == "growing"
    assert schedule.status(p, day(8)) == "ready"
    assert schedule.status(p, day(10)) == "ready"
    assert schedule.status(p, day(11)) == "overdue"


def test_harvest_is_date_driven_even_when_never_uncovered() -> None:
    assert schedule.status(planting(), day(8)) == "ready"


def test_crop_without_blackout_starts_growing() -> None:
    p = planting(crop=Crop(name="Cress", color="#43a047", cover_days=0, light_days=6))
    assert schedule.status(p, day(0)) == "growing"
    assert [t.kind for t in schedule.tasks_for_planting(p, day(0))] == []


def test_planned_is_planned_until_confirmed() -> None:
    p = planting(sown_on=day(5), planned=True, last_watered_on=None)
    assert schedule.status(p, day(0)) == "planned"
    assert schedule.status(p, day(20)) == "planned"
    assert schedule.computed(p, day(0))["day"] == 0
    assert schedule.progress(p, day(20)) == 0.0


def test_watering_due_from_last_watering() -> None:
    p = planting()
    assert schedule.water_due_on(p) == day(1)
    assert not schedule.computed(p, day(0))["needs_water"]
    assert schedule.computed(p, day(1))["needs_water"]
    p.last_watered_on = day(1)
    assert not schedule.computed(p, day(1))["needs_water"]


def test_no_watering_schedule_when_interval_is_zero() -> None:
    p = planting(crop=Crop(name="X", color="#43a047", water_every_days=0))
    assert schedule.water_due_on(p) is None
    assert not any(t.kind == "water" for t in schedule.tasks_for_planting(p, day(5)))


def test_tasks_through_a_grow() -> None:
    p = planting()
    kinds = lambda n: sorted(t.kind for t in schedule.tasks_for_planting(p, day(n)))  # noqa: E731
    assert kinds(0) == []
    assert kinds(1) == ["water"]
    assert kinds(3) == ["uncover", "water"]
    uncover = next(t for t in schedule.tasks_for_planting(p, day(4)) if t.kind == "uncover")
    assert uncover.late and uncover.due_on == day(3)
    p.uncovered_on = day(3)
    p.last_watered_on = day(8)
    assert kinds(8) == ["harvest"]
    harvest = schedule.tasks_for_planting(p, day(10))[0]
    assert harvest.last_day and not harvest.late
    harvest = schedule.tasks_for_planting(p, day(11))[0]
    assert harvest.late and not harvest.last_day


def test_uncover_task_drops_once_the_window_opens() -> None:
    p = planting(last_watered_on=day(8))
    assert [t.kind for t in schedule.tasks_for_planting(p, day(8))] == ["harvest"]


def test_planned_tasks_soak_then_sow() -> None:
    p = planting(sown_on=day(5), planned=True, last_watered_on=None, crop=Crop(name="Pea", color="#43a047", soak_hours=12))
    assert schedule.tasks_for_planting(p, day(3)) == []
    assert [t.kind for t in schedule.tasks_for_planting(p, day(4))] == ["soak"]
    assert [t.kind for t in schedule.tasks_for_planting(p, day(5))] == ["soak", "sow"]
    p.soaked_on = day(4)
    assert [t.kind for t in schedule.tasks_for_planting(p, day(6))] == ["sow"]
    assert schedule.tasks_for_planting(p, day(6))[0].late


def test_task_order_is_kind_then_plot_order() -> None:
    plots = [Plot("B", "B", order=0), Plot("A1", "A1", order=1)]
    a = planting(id="a", plot_id="A1")
    b = planting(id="b", plot_id="B", sown_on=day(-7))
    tasks = schedule.tasks([a, b], plots, day(3))
    assert [(t.kind, t.plot_id) for t in tasks] == [
        ("harvest", "B"),
        ("uncover", "A1"),
        ("water", "B"),
        ("water", "A1"),
    ]


def test_overlap_allows_same_day_turnover() -> None:
    a = planting()
    b = planting(id="b", sown_on=schedule.times(a).harvest_end, planned=True)
    assert not schedule.overlaps(a, b, day(0))
    c = planting(id="c", sown_on=day(9), planned=True)
    assert schedule.overlaps(a, c, day(0))


def test_late_harvest_holds_the_plot_until_today() -> None:
    a = planting()
    b = planting(id="b", sown_on=day(12), planned=True)
    assert not schedule.overlaps(a, b, day(5))
    assert schedule.overlaps(a, b, day(14))


def test_current_prefers_the_sown_planting() -> None:
    sown = planting()
    plan1 = planting(id="n1", sown_on=day(20), planned=True)
    plan2 = planting(id="n2", sown_on=day(12), planned=True)
    cur, nxt = schedule.current_for_plot([plan1, sown, plan2], "A1")
    assert (cur.id, nxt.id) == ("p1", "n2")
    cur, nxt = schedule.current_for_plot([plan1, plan2], "A1")
    assert (cur.id, nxt.id) == ("n2", "n1")
    assert schedule.current_for_plot([], "A1") == (None, None)
    assert schedule.plot_status([], "A1", D) == "empty"


def test_reminder_skips_an_early_harvest_only() -> None:
    assert not schedule.reminder_worthy(schedule.Task("harvest", "p", "A1", D))
    assert schedule.reminder_worthy(schedule.Task("harvest", "p", "A1", D, last_day=True))
    assert schedule.reminder_worthy(schedule.Task("harvest", "p", "A1", D, late=True))
    assert schedule.reminder_worthy(schedule.Task("water", "p", "A1", D))


def test_computed_is_json_ready() -> None:
    c = schedule.computed(planting(uncovered_on=day(3)), day(4))
    assert c == {
        "status": "growing",
        "soak_on": None,
        "uncover_on": "2026-10-04",
        "harvest_start": "2026-10-09",
        "harvest_end": "2026-10-11",
        "total_days": 8,
        "day": 5,
        "progress": 0.5,
        "water_due_on": "2026-10-02",
        "needs_water": True,
        "days_to_harvest": 4,
    }
