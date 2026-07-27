import pytest

from domain.go_setup import RemoteGoSetup, is_go_zip_name, looks_like_go_name, parse_go_entry


# --- looks_like_go_name / is_go_zip_name -------------------------------------


def test_looks_like_go_name_matches_prefix_case_insensitively():
    assert looks_like_go_name("GO-ORECA-07.zip") is True
    assert looks_like_go_name("go-oreca-07.zip") is True
    assert looks_like_go_name("Go-Oreca-07.zip") is True


def test_looks_like_go_name_rejects_non_go_prefix():
    assert looks_like_go_name("HYMO-Spa_Porsche_id_1.zip") is False
    assert looks_like_go_name("readme.txt") is False


def test_is_go_zip_name_requires_zip_extension():
    assert is_go_zip_name("GO-Something.zip") is True
    assert is_go_zip_name("GO-Something.rar") is False
    assert is_go_zip_name("GO-Something") is False


def test_is_go_zip_name_case_insensitive_extension():
    assert is_go_zip_name("GO-Something.ZIP") is True


# --- parse_go_entry -----------------------------------------------------------


def test_parse_go_entry_valid_three_segments():
    result = parse_go_entry("GO-ORECA.zip", "/lmu-setups/oreca/imola/go-oreca.zip", ["Oreca 07", "Imola", "GO-ORECA.zip"])
    assert result == RemoteGoSetup(
        name="GO-ORECA.zip",
        path_lower="/lmu-setups/oreca/imola/go-oreca.zip",
        car="Oreca 07",
        track="Imola",
    )


@pytest.mark.parametrize("name,path,segments", [
    ("GO-ORECA.zip", "/x/go-oreca.zip", ["GO-ORECA.zip"]),                                             # one segment
    ("GO-ORECA.zip", "/x/oreca/go-oreca.zip", ["Oreca 07", "GO-ORECA.zip"]),                            # two segments
    ("GO-ORECA.zip", "/x/go-oreca.zip", ["Oreca 07", "Imola", "extra", "GO-ORECA.zip"]),                # four segments
    ("HYMO-Spa_id_1.zip", "/x/spa/hymo.zip", ["Porsche", "Spa", "HYMO-Spa_id_1.zip"]),                  # non-GO name
    ("GO-ORECA.txt", "/x/go-oreca.txt", ["Oreca 07", "Imola", "GO-ORECA.txt"]),                         # non-zip
])
def test_parse_go_entry_rejects_invalid_input(name, path, segments):
    assert parse_go_entry(name, path, segments) is None
