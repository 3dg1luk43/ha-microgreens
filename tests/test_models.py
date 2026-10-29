"""Model loading, write validation and the 0.1.x import (models.py). Pure."""
from __future__ import annotations

from datetime import date

import pytest

from custom_components.ha_microgreens.models import (
    GardenData,
    MicrogreensError,
    Profile,
    clean_plot,
    clean_profile,
    migrate_legacy,
    slugify,
)

# A 0.1.x store as the old integration wrote it (.storage/microgreens "data").
LEGACY = {
    "plots": [{"id": f"A{i}", "label": f"Plot A{i}"} for i in range(1, 4)] + [{"id": "A1", "label": "dupe"}],
    "profiles": [
        {"id": "rukola", "name": "Rukola", "cover_days": 3, "uncover_days": 8, "watering_frequency_days": 1, "notes": "Fast"},
        {"id": "hrasek", "name": "Hrášek", "cover_days": 5, "uncover_days": 16, "watering_frequency_days": 2, "notes": ""},
    ],
    "deployments": [
        {
            "plot_id": "A1",
            "sticker": "A1-2410",
            "plant_id": "rukola",
            "plant_name": "Rukola",
            "start_date": "2026-10-20",
            "cover_end": "2026-10-23",
            "harvest_date": "2026-10-31",
            "watering_every_days": 1,
            "next_watering_due": "2026-10-29",
            "notes": "Fast",
        },
        {
            "plot_id": "A2",
            "sticker": "A2",
            "plant_id": "hrasek",
            "plant_name": "Hrášek",
            "start_date": "2026-11-02",
            "cover_end": "2026-11-07",
            "harvest_date": "2026-11-23",
            "watering_every_days": 2,
            "next_watering_due": "2026-11-04",
        },
        {"plot_id": "ZZ", "start_date": "2026-10-01"},  # unknown plot: skipped
        {"plot_id": "A3", "start_date": "not a date"},  # unreadable: skipped
    ],
}


def test_legacy_import_keeps_everything_readable() -> None:
    data = migrate_legacy(LEGACY, date(2026, 10, 29))
    assert [p.id for p in data.plots] == ["A1", "A2", "A3"]
    assert data.plots[0].name == "Plot A1"
    rukola = data.profile("rukola")
    assert (rukola.cover_days, rukola.light_days, rukola.water_every_days, rukola.notes) == (3, 8, 1, "Fast")
    assert data.profile("hrasek").name == "Hrášek"
    assert len(data.plantings) == 2
    a1 = next(p for p in data.plantings if p.plot_id == "A1")
    assert a1.sown_on == date(2026, 10, 20)
    assert (a1.crop.cover_days, a1.crop.light_days) == (3, 8)
    assert a1.label == "A1-2410"
    assert a1.uncovered_on == date(2026, 10, 23)  # past cover_end: taken as uncovered
    assert a1.last_watered_on == date(2026, 10, 28)
    assert not a1.planned
    a2 = next(p for p in data.plantings if p.plot_id == "A2")
    assert a2.planned and a2.uncovered_on is None and a2.last_watered_on is None
    assert data.meta["legacy_imported_on"] == "2026-10-29"


def test_legacy_import_survives_garbage() -> None:
    data = migrate_legacy({"plots": "nope", "profiles": [None, 3], "deployments": [{}]}, date(2026, 1, 1))
    assert data.plots == [] and data.profiles == [] and data.plantings == []
    assert migrate_legacy(None, date(2026, 1, 1)).plots == []


def test_store_round_trip() -> None:
    data = migrate_legacy(LEGACY, date(2026, 10, 29))
    again = GardenData.from_store(data.to_store())
    assert again.to_store() == data.to_store()


def test_from_store_drops_only_unreadable_rows() -> None:
    data = GardenData.from_store(
        {
            "plots": [{"id": "A1", "name": "A1"}, {"id": "A1", "name": "dupe"}],
            "plantings": [{"plot_id": "A1", "sown_on": "2026-10-01"}, {"plot_id": "A1"}, "junk"],
            "history": [{"sown_on": "2026-10-01"}],
        }
    )
    assert len(data.plots) == 1
    assert len(data.plantings) == 1
    assert data.history == []


def test_clean_profile_creates_with_a_slug_and_updates_in_place() -> None:
    created = clean_profile({"name": "Red Cabbage", "cover_days": 2, "light_days": 9}, [])
    assert created.id == "red_cabbage"
    assert (created.cover_days, created.light_days, created.harvest_window_days) == (2, 9, 3)
    updated = clean_profile({"id": "red_cabbage", "name": "Red cabbage", "light_days": "10"}, [created])
    assert updated.id == "red_cabbage" and updated.light_days == 10 and updated.cover_days == 2
    again = clean_profile({"name": "Red Cabbage"}, [created])
    assert again.id == "red_cabbage_2"


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        ({"name": ""}, "invalid_name"),
        ({"name": "x" * 61}, "invalid_name"),
        ({"name": "X", "light_days": 0}, "invalid_number"),
        ({"name": "X", "cover_days": 2.5}, "invalid_number"),
        ({"name": "X", "cover_days": "abc"}, "invalid_number"),
        ({"name": "X", "color": "red"}, "invalid_color"),
        ({"name": "X", "seed_grams": -1}, "invalid_number"),
    ],
)
def test_clean_profile_refuses(raw, key) -> None:
    with pytest.raises(MicrogreensError) as err:
        clean_profile(raw, [])
    assert err.value.key == key


def test_clean_plot() -> None:
    plot, created = clean_plot({"id": "B1", "name": "Top shelf left", "location": "Rack"}, [])
    assert created and plot.id == "B1" and plot.order == 0
    renamed, created = clean_plot({"id": "B1", "name": "Renamed"}, [plot])
    assert not created and renamed.name == "Renamed" and renamed.location == "Rack"
    with pytest.raises(MicrogreensError) as err:
        clean_plot({"id": "b1", "name": "Case clash"}, [plot])
    assert err.value.key == "plot_exists"
    with pytest.raises(MicrogreensError) as err:
        clean_plot({"id": "has space", "name": "x"}, [])
    assert err.value.key == "invalid_id"


def test_slugify_folds_accents() -> None:
    assert slugify("Ředkvička", "x") == "redkvicka"
    assert slugify("!!!", "crop") == "crop"


def test_profile_total_days() -> None:
    assert Profile(id="a", name="A", color="#000000", cover_days=3, light_days=7).total_days == 10
