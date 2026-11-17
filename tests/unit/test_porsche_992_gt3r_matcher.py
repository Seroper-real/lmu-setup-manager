"""Tests for commit 74473e7: "Porsche 911 GT3 R" matched as the "Porsche 992"
lmgt3 entry via the new `911.*gt3` matcher in config/mapping.json.

These run against the REAL bundled config/mapping.json (not a fixture copy),
because the behaviour under test is the interaction between the new regex and
its position in the ordered cars list.
"""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = REPO_ROOT / "config" / "mapping.json"


@pytest.fixture
def real_car_manager(mocker):
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", False)
    mocker.patch("processing.car_manager.get_path", return_value=MAPPING_PATH)
    from processing.car_manager import CarManager
    return CarManager()


def _entry(name):
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    return next(e for e in data["cars"] if e["name"] == name)


# --- mapping.json shape ------------------------------------------------------


def test_mapping_json_is_valid_and_has_cars_section():
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    assert isinstance(data["cars"], list) and data["cars"]


def test_porsche_992_entry_keeps_original_matcher_and_adds_gt3_alternative():
    entry = _entry("Porsche 992")
    assert entry["class"] == "lmgt3"
    assert entry["matcher"][0] == "992"
    assert "911.*gt3" in entry["matcher"]
    assert len(entry["matcher"]) == 2


def test_every_car_matcher_in_mapping_json_compiles():
    # A bad regex is silently skipped at runtime (compile_patterns logs and
    # moves on), so a typo in the new pattern would lose the match without
    # any visible error. Catch that here.
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    for entry in data["cars"]:
        for raw in entry.get("matcher", []):
            re.compile(raw, re.IGNORECASE)


def test_porsche_992_is_still_the_only_entry_with_the_gt3_alternative():
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    owners = [e["name"] for e in data["cars"] if "911.*gt3" in e.get("matcher", [])]
    assert owners == ["Porsche 992"]


# --- the reported case and its spelling variants -----------------------------


@pytest.mark.parametrize("query", [
    "Porsche 911 GT3 R LMGT3",
    "Porsche 911 GT3 R",
    "PORSCHE 911 GT3 R",                  # case-insensitive
    "porsche 911 gt3 r lmgt3",
    "911GT3R",                            # no separators
    "911 - GT3 R",
    "Porsche 911 GT3 R (2026)",           # trailing noise
    "Porsche 911 GT3 R Setup",
    "  Porsche 911 GT3 R  ",              # surrounding whitespace is stripped
])
def test_911_gt3_r_variants_resolve_to_porsche_992(real_car_manager, query):
    assert real_car_manager.get_car_name(query) == "Porsche 992"


def test_911_gt3_r_resolves_to_lmgt3_class(real_car_manager):
    name = real_car_manager.get_car_name("Porsche 911 GT3 R LMGT3")
    assert real_car_manager.get_car_class(name) == "GT3"


def test_porsche_992_class_and_sort_rank_unchanged(real_car_manager):
    assert real_car_manager.get_car_class("Porsche 992") == "GT3"
    # lmgt3 sits at index 4 of _CLASS_ORDER.
    assert real_car_manager.get_class_rank("Porsche 992") == 4


def test_get_all_cars_lists_porsche_992_once_with_gt3_class(real_car_manager):
    matches = [c for c in real_car_manager.get_all_cars() if c["name"] == "Porsche 992"]
    assert matches == [{"name": "Porsche 992", "carClass": "GT3"}]


# --- existing 992 matching must not regress ----------------------------------


@pytest.mark.parametrize("query", [
    "Porsche 992 GT3 R",
    "Porsche 992 LMGT3R",
    "992GT3 LMGT3",
    "Porsche 992 LMGT3R Setup",
])
def test_existing_992_matches_still_resolve(real_car_manager, query):
    assert real_car_manager.get_car_name(query) == "Porsche 992"


# --- must not capture unrelated cars ------------------------------------------


@pytest.mark.parametrize("query", [
    "Porsche 911 GT2 RS",   # no "gt3" -> the new alternative must not fire
    "GT3 R Porsche",        # gt3 before 911: the pattern is ordered 911 -> gt3
])
def test_names_without_911_before_gt3_are_not_porsche_992(real_car_manager, query):
    assert real_car_manager.get_car_name(query) != "Porsche 992"


@pytest.mark.parametrize("query, expected", [
    ("Porsche 911 RSR-19", "Porsche 911"),
    ("Porsche 911 RSR-19 Setup", "Porsche 911"),
])
def test_lmgte_porsche_911_rsr_is_unaffected(real_car_manager, query, expected):
    assert real_car_manager.get_car_name(query) == expected
    assert real_car_manager.get_car_class(expected) == "GTE"


def test_unrelated_cars_are_unaffected(real_car_manager):
    assert real_car_manager.get_car_name("Ferrari 499P") == "Ferrari 499P"
    assert real_car_manager.get_car_name("Porsche 963") == "Porsche 963"
    assert real_car_manager.get_car_name("Corvette Z06 GT3.R") == "Corvette Z06"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Known regression from 74473e7: 'Porsche 911 RSR-19 GT3' now resolves to "
        "lmgt3 'Porsche 992' because '911.*gt3' is checked before the lmgte "
        "'911.*rsr' entry. Before the commit it resolved to 'Porsche 911' (GTE). "
        "Remove this xfail once the matcher is fixed."
    ),
)
def test_rsr_name_containing_gt3_stays_lmgte(real_car_manager):
    assert real_car_manager.get_car_name("Porsche 911 RSR-19 GT3") == "Porsche 911"


# --- manual-upload filename path uses the same matcher ------------------------


def test_manual_upload_filename_with_911_gt3r_resolves_car(real_car_manager):
    from processing.manual_upload import guess_car_track_from_filename

    track_manager = MagicMock()
    track_manager.get_official_track_name.return_value = "Spa-Francorchamps"

    car, track = guess_car_track_from_filename(
        "GO-911-GT3R-LMGT3-SPA.zip", real_car_manager, track_manager
    )

    assert car == "Porsche 992"
    assert track == "Spa-Francorchamps"


# --- remote mapping precedence still applies ----------------------------------


def test_remote_copy_of_mapping_with_new_matcher_is_used_when_reachable(mocker):
    # The remote mirror wins over the bundled file, so the same matcher must
    # work when it arrives via the remote payload too.
    remote = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = remote
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_ENABLED", True)
    mocker.patch("processing.car_manager.REMOTE_MAPPINGS_TIMEOUT", 5)
    mocker.patch("processing.car_manager.get_path", return_value=MAPPING_PATH)
    mocker.patch("processing.catalog_loader.requests.get", return_value=resp)
    mocker.patch("processing.catalog_loader._remote_cache", {})

    from processing.car_manager import CarManager
    mgr = CarManager()

    assert mgr.get_car_name("Porsche 911 GT3 R LMGT3") == "Porsche 992"
