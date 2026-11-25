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


# --- parse_go_version / filter_latest_go_version ------------------------------

from pathlib import Path

from domain.go_setup import filter_latest_go_version, parse_go_version


@pytest.mark.parametrize("name, expected", [
    pytest.param("GO V1.4.3 9X8EVO HYP MON Q Safe.svm", (1, 4, 3), id="typical"),
    pytest.param("GO v1.4.3 x.svm", (1, 4, 3), id="lowercase_v"),
    pytest.param("GO V1.10.0 x.svm", (1, 10, 0), id="multi_digit_component"),
    pytest.param("GO V2 x.svm", (2,), id="single_component"),
    pytest.param("GO V1.4 x.svm", (1, 4), id="two_components"),
    pytest.param("GO V1.4.3.svm", (1, 4, 3), id="version_before_extension"),
    pytest.param("GO x.svm", None, id="no_version"),
    pytest.param("GO EVO Q Safe.svm", None, id="v_inside_word_ignored"),
    pytest.param("GOV1.4.3.svm", None, id="v_glued_to_letters_ignored"),
    pytest.param("", None, id="empty"),
])
def test_parse_go_version(name, expected):
    assert parse_go_version(name) == expected


def _p(*names):
    return [Path(n) for n in names]


def test_filter_keeps_only_highest_version():
    files = _p("GO V1.4.3 a.svm", "GO V1.4.1 a.svm", "GO V1.3.3 a.svm")
    assert filter_latest_go_version(files) == [files[0]]


def test_filter_numeric_not_lexicographic():
    files = _p("GO V1.4.3 a.svm", "GO V1.10.0 a.svm", "GO V1.9.9 a.svm")
    assert filter_latest_go_version(files) == [files[1]]


def test_filter_keeps_all_files_of_the_top_version_and_preserves_order():
    files = _p("GO V1.4.3 b.svm", "GO V1.3.0 b.svm", "GO V1.4.3 a.svm", "GO V1.4.3 c.svm")
    assert filter_latest_go_version(files) == [files[0], files[2], files[3]]


def test_filter_is_global_variants_only_in_older_versions_dropped():
    files = _p("GO V1.4.3 a.svm", "GO V1.3.3 onlyold.svm")
    assert filter_latest_go_version(files) == [files[0]]


def test_filter_zero_padding_treats_1_4_and_1_4_0_as_equal():
    files = _p("GO V1.4 a.svm", "GO V1.4.0 b.svm", "GO V1.3.9 c.svm")
    assert filter_latest_go_version(files) == files[:2]


def test_filter_padding_does_not_hide_higher_patch():
    files = _p("GO V1.4 a.svm", "GO V1.4.1 b.svm")
    assert filter_latest_go_version(files) == [files[1]]


def test_filter_unversioned_files_always_kept():
    files = _p("GO V1.4.3 a.svm", "GO V1.2.0 b.svm", "notes.svm")
    assert filter_latest_go_version(files) == [files[0], files[2]]


def test_filter_no_versions_returns_everything():
    files = _p("a.svm", "b.svm")
    assert filter_latest_go_version(files) == files


def test_filter_empty_list():
    assert filter_latest_go_version([]) == []


def test_filter_returns_new_list_when_no_versions():
    files = _p("a.svm")
    assert filter_latest_go_version(files) is not files


def test_filter_same_name_in_different_dirs_both_kept():
    files = [Path("x/GO V1.4.3 a.svm"), Path("y/GO V1.4.3 a.svm"), Path("x/GO V1.0.0 a.svm")]
    assert filter_latest_go_version(files) == files[:2]


@pytest.mark.parametrize("name, expected", [
    ("HYMO 1.3.3 TR010 IMO CQ.svm", (1, 3, 3)),
    ("hymo 1.10.0 x.svm", (1, 10, 0)),
    ("HYMO TR010 IMO CQ.svm", None),
])
def test_parse_hymo_version(name, expected):
    assert parse_go_version(name) == expected
