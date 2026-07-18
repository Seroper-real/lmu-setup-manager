import pytest
from domain.setup import Setup


def _make(
    id="abc-123",
    title="Test Setup",
    car="Ferrari 499P",
    track="Le Mans/Bugatti",
    hotlap=None,
    last_updated=1000,
    is_bundle=False,
    combos=None,
):
    if combos is None:
        combos = [{"car": {"name": car}, "track": {"name": track}}]
    return Setup({
        "id": id,
        "title": title,
        "setupCombos": combos,
        "hotlapLink": hotlap,
        "lastUpdatedAt": last_updated,
        "isBundle": is_bundle,
    })


def test_id():
    assert _make(id="abc-123").id == "abc-123"


def test_title():
    assert _make(title="My Setup").title == "My Setup"


def test_car():
    assert _make(car="Ferrari 499P").car == "Ferrari 499P"


def test_track():
    assert _make(track="Le Mans/Bugatti").track == "Le Mans/Bugatti"


def test_safe_track_replaces_slash():
    assert _make(track="Le Mans/Bugatti").safe_track == "Le Mans_Bugatti"


def test_safe_track_replaces_backslash():
    assert _make(track="A\\B").safe_track == "A_B"


def test_safe_track_replaces_hyphen():
    assert _make(track="Spa-Francorchamps").safe_track == "Spa_Francorchamps"


def test_safe_track_setter():
    s = _make()
    s.safe_track = "custom"
    assert s.safe_track == "custom"


def test_hotlap_link_none():
    assert _make(hotlap=None).hotlap_link is None


def test_hotlap_link_value():
    assert _make(hotlap="https://example.com").hotlap_link == "https://example.com"


def test_last_updated():
    assert _make(last_updated=9999).last_updated == 9999


def test_is_bundle_false():
    assert _make(is_bundle=False).is_bundle is False


def test_is_bundle_true():
    assert _make(is_bundle=True).is_bundle is True


def test_combo_returns_first_element():
    s = _make()
    s.data["setupCombos"].append({"car": {"name": "Other"}, "track": {"name": "Other"}})
    assert s.combo["car"]["name"] == "Ferrari 499P"


def test_empty_combos_raises_on_init():
    with pytest.raises(IndexError):
        _make(combos=[])


def test_safe_car_replaces_space_and_slash():
    assert _make(car="Porsche/963 LMDh").safe_car == "Porsche_963_LMDh"


def test_remote_filename_format():
    s = _make(id="abc-123", car="Ferrari 499P", track="Le Mans/Bugatti", last_updated=1700000000)
    assert s.remote_filename == "HYMO-Le_Mans_Bugatti_Ferrari_499P_abc-123_1700000000.zip"


def test_remote_relative_path_nests_under_car():
    s = _make(id="abc-123", car="Ferrari 499P", track="Le Mans/Bugatti", last_updated=1700000000)
    assert s.remote_relative_path == "Ferrari_499P/HYMO-Le_Mans_Bugatti_Ferrari_499P_abc-123_1700000000.zip"


def test_parse_remote_zip_name_roundtrip():
    from domain.setup import parse_remote_zip_name
    s = _make(id="abc-123", car="Ferrari 499P", track="Le Mans/Bugatti", last_updated=1700000000)
    assert parse_remote_zip_name(s.remote_filename) == ("abc-123", 1700000000)


def test_parse_remote_zip_name_with_underscores_in_names():
    from domain.setup import parse_remote_zip_name
    # track/car may contain underscores; id (UUID-like, no underscores) + digit ts
    # are still recovered by the right-anchored match.
    assert parse_remote_zip_name("HYMO-Road_Atlanta_BMW_M_Hybrid_V8_uuid-99_42.zip") == ("uuid-99", 42)


def test_parse_remote_zip_name_invalid():
    from domain.setup import parse_remote_zip_name
    assert parse_remote_zip_name("not-a-setup.txt") is None
    assert parse_remote_zip_name("HYMO-missing_ts_field.zip") is None


def test_parse_remote_zip_name_without_hymo_prefix_is_ignored():
    from domain.setup import parse_remote_zip_name
    # A conforming name lacking the HYMO- brand (e.g. manually dropped by a
    # human) must not be picked up.
    assert parse_remote_zip_name("Road_Atlanta_BMW_M_Hybrid_V8_uuid-99_42.zip") is None
