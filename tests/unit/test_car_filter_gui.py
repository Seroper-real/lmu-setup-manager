"""Static + API-contract tests for the car filter GUI section (src/gui/web).

No JS runtime is available, so app.js / i18n.js are checked textually and the
Python API the JS depends on is exercised for real.
"""
import json
import re
from pathlib import Path

import pytest

import core.settings_db as settings_db

WEB = Path(__file__).resolve().parents[2] / "src" / "gui" / "web"
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
I18N_JS = (WEB / "i18n.js").read_text(encoding="utf-8")

CAR_KEYS = [
    "carFilterTitle", "carFilterAllLabel", "carFilterHintAll", "carFilterHintSelected",
    "carFilterSearchPlaceholder", "carFilterSelectAll", "carFilterDeselectAll",
    "carFilterCounter", "carFilterEmpty", "carFilterOtherClass",
    "carFilterLoadError", "carFilterSaveError",
    "carFilterDesc", "carFilterColName", "carFilterColClass",
]
FUNCTION_KEYS = {"carFilterCounter"}
CAR_FUNCS = [
    "refreshCarFilter", "saveCarFilter", "changeCarFilter", "carClassRank", "carFilterCountText",
    "updateCarFilterCount", "renderCarFilterList", "renderCarFilterSection",
    "renderCarFilterView", "getCarFilterViewModel",
]


def _extra_block(lang: str) -> str:
    """Body of EXTRA.<lang> = { ... }, brace matched with string awareness."""
    start = I18N_JS.index("const EXTRA = {")
    m = re.compile(r"^  %s: \{" % lang, re.M).search(I18N_JS, start)
    assert m, f"EXTRA.{lang} not found"
    depth, i = 1, m.end()
    in_str = None
    while depth:
        ch = I18N_JS[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == in_str:
                in_str = None
        elif ch in "\"'`":
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        i += 1
    return I18N_JS[m.end():i]


@pytest.fixture(scope="module")
def blocks() -> dict[str, str]:
    return {"it": _extra_block("it"), "en": _extra_block("en")}


def _value(block: str, key: str) -> str:
    m = re.search(r"^\s*%s:\s*(.+?),\s*$" % key, block, re.M)
    assert m, f"{key} missing"
    return m.group(1)


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("key", CAR_KEYS)
def test_i18n_key_present_and_nonempty(blocks, lang, key):
    assert _value(blocks[lang], key) not in ('""', "''", "``")


@pytest.mark.parametrize("key", CAR_KEYS)
def test_i18n_value_kind_consistent(blocks, key):
    kinds = {lang: _value(blocks[lang], key).lstrip().startswith("(") for lang in blocks}
    assert kinds["it"] == kinds["en"] == (key in FUNCTION_KEYS)


def test_i18n_counter_uses_both_args(blocks):
    for lang in blocks:
        v = _value(blocks[lang], "carFilterCounter")
        assert re.match(r"\(\s*n\s*,\s*m\s*\)\s*=>", v)
        assert "${n}" in v and "${m}" in v


def test_i18n_no_duplicate_keys_in_blocks(blocks):
    for lang, b in blocks.items():
        for key in CAR_KEYS:
            assert len(re.findall(r"^\s*%s:" % key, b, re.M)) == 1, (lang, key)


def test_i18n_keys_used_by_app_match_defined():
    used = set(re.findall(r'"(carFilter\w+)"', APP_JS))
    assert used == set(CAR_KEYS), (used ^ set(CAR_KEYS))


def _strip(src: str) -> str:
    """Drop comments and string/template literal text (keeping ${...} expressions)
    so bracket counting is not fooled by literal contents."""
    out: list[str] = []
    i, n = 0, len(src)
    stack: list[str] = []  # "`" template, "{" brace or ${ } expression
    while i < n:
        ch = src[i]
        top = stack[-1] if stack else None
        if top == "`":
            if ch == "\\":
                i += 2
                continue
            if ch == "`":
                stack.pop()
            elif ch == "$" and src[i + 1:i + 2] == "{":
                stack.append("{")
                out.append("{")
                i += 2
                continue
            i += 1
            continue
        if ch == "/" and src[i + 1:i + 2] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if ch == "/" and src[i + 1:i + 2] == "*":
            i = src.index("*/", i) + 2
            continue
        if ch in "\"'":
            q = ch
            i += 1
            while src[i] != q:
                i += 2 if src[i] == "\\" else 1
            i += 1
            continue
        if ch == "`":
            stack.append("`")
            i += 1
            continue
        if ch == "{":
            stack.append("{")
        elif ch == "}" and top == "{":
            stack.pop()
        out.append(ch)
        i += 1
    assert not stack, f"unterminated template/brace: {stack}"
    return "".join(out)


def _balanced(src: str) -> bool:
    try:
        text = _strip(src)
    except (ValueError, IndexError, AssertionError):
        return False
    pairs = {")": "(", "]": "[", "}": "{"}
    st: list[str] = []
    for ch in text:
        if ch in "([{":
            st.append(ch)
        elif ch in pairs:
            if not st or st.pop() != pairs[ch]:
                return False
    return not st


def _function_source(name: str) -> str:
    m = re.search(r"^(?:async )?function %s\(" % name, APP_JS, re.M)
    assert m, f"function {name} not found"
    end = re.compile(r"^}\s*$", re.M).search(APP_JS, m.end())
    assert end, f"end of {name} not found"
    return APP_JS[m.start():end.end()]


def test_i18n_file_balanced():
    assert _balanced(I18N_JS)


# Whole-file balance is deliberately not asserted: app.js contains regex literals
# (e.g. /[`$]/) that the small lexer above does not model; the per-function checks
# below cover the new code.


@pytest.mark.parametrize("fn", CAR_FUNCS)
def test_app_car_filter_functions_balanced(fn):
    assert _balanced(_function_source(fn)), fn


def test_app_calls_backend_api():
    assert re.search(r"api\(\)\.get_car_filter\(", APP_JS)
    assert re.search(r"api\(\)\.set_car_filter\(\s*snapshot\.all\s*,\s*snapshot\.selected\s*\)", APP_JS)


def test_app_backend_methods_exist_on_api():
    from gui.api import Api
    assert callable(Api.get_car_filter) and callable(Api.set_car_filter)


def test_app_dom_ids_rendered_and_bound():
    for dom_id in ["car-filter-all", "car-filter-search", "car-filter-count",
                   "car-filter-select-all", "car-filter-deselect-all"]:
        assert f'id="{dom_id}"' in APP_JS, dom_id
    for dom_id in ["car-filter-all", "car-filter-search", "car-filter-select-all", "car-filter-deselect-all"]:
        assert f'getElementById("{dom_id}")' in APP_JS, dom_id
    assert "[data-car-name]" in APP_JS
    assert 'id="car-filter-section"' in APP_JS
    assert 'getElementById("car-filter-section")' in APP_JS


def test_app_css_classes_defined():
    css = (WEB / "styles.css").read_text(encoding="utf-8")
    classes = set(re.findall(r"\b(car-filter-[\w-]+)", APP_JS)) - {
        "car-filter-all", "car-filter-search", "car-filter-count", "car-filter-select-all",
        "car-filter-deselect-all", "car-filter-section", "car-filter-groups",
        "car-filter-prev-page", "car-filter-next-page",
    }
    assert classes
    for cls in classes:
        assert f".{cls}" in css, cls


def test_app_refresh_wired_on_view_entry():
    assert re.search(r"refreshCarFilter\(\)", APP_JS)
    assert APP_JS.count("refreshCarFilter()") >= 2  # definition + at least one call


def test_app_rollback_on_error_present():
    fn = _function_source("saveCarFilter")
    assert "catch" in fn and "carFilterSaveError" in fn
    assert "carFilterConfirmed.all" in fn and "carFilterConfirmed.selected" in fn
    # Saves are serialized and only the newest failed change rolls back.
    assert "carFilterSaveChain.then(" in fn and "seq === carFilterSaveSeq" in fn


def test_app_search_input_only_rerenders_list():
    """Typing must not rebuild the search input (it would lose focus/caret)."""
    fn = _function_source("renderCarFilterSection")
    m = re.search(r'getElementById\("car-filter-search"\)\.addEventListener\("input",(.*?)\}\);', fn, re.S)
    assert m
    assert "renderCarFilterList()" in m.group(1)
    assert "renderCarFilterSection" not in m.group(1)
    assert "car-filter-search" not in _function_source("renderCarFilterList")


def test_app_changes_blocked_until_loaded():
    assert "if (!state.carFilter.loaded) return" in _function_source("changeCarFilter")
    assert "loaded: true" in _function_source("refreshCarFilter")


def test_app_class_order_matches_car_manager_labels():
    from processing.car_manager import CarManager
    m = re.search(r"const CAR_CLASS_ORDER = \[(.*?)\];", APP_JS)
    assert m
    js_order = re.findall(r'"([^"]+)"', m.group(1))
    expected: list[str] = []
    for raw in CarManager._CLASS_ORDER:
        label = CarManager._CLASS_LABELS[raw].lower()
        if label not in expected:
            expected.append(label)
    assert js_order == expected


# ----- real Python API, with the shapes the JS relies on ---------------------


@pytest.fixture
def api(mocker):
    from gui.api import Api
    mocker.patch.object(Api, "_reload_config")
    return Api()


def test_get_car_filter_shape_real_catalog(api):
    got = api.get_car_filter()
    assert set(got) == {"all", "selected", "cars"}
    assert got["all"] is True and got["selected"] == []
    assert got["cars"], "mapping.json should declare cars"
    for c in got["cars"]:
        assert set(c) == {"name", "carClass"}
        assert isinstance(c["name"], str)
        assert c["carClass"] is None or isinstance(c["carClass"], str)


def test_on_to_off_sends_full_name_list(api):
    names = [c["name"] for c in api.get_car_filter()["cars"]]
    api.set_car_filter(False, names)
    got = api.get_car_filter()
    assert got["all"] is False
    assert got["selected"] == list(dict.fromkeys(names))
    assert settings_db.get_config()["cars"]["all"] is False


def test_off_to_on_keeps_selection_and_is_json_serializable(api):
    api.set_car_filter(False, ["A", "B"])
    api.set_car_filter(True, ["A", "B"])
    got = json.loads(json.dumps(api.get_car_filter()))
    assert got["all"] is True and got["selected"] == ["A", "B"]


def test_deselect_all_is_empty_selection_not_all(api):
    api.set_car_filter(False, [])
    got = api.get_car_filter()
    assert got["all"] is False and got["selected"] == []


@pytest.mark.parametrize("bad", [("yes", []), (True, "A"), (False, [1]), (None, [])])
def test_set_car_filter_rejects_bad_shapes(api, bad):
    with pytest.raises(ValueError):
        api.set_car_filter(*bad)


# ----- dedicated "Selected cars" view ----------------------------------------

VIEW_KEYS = ["navCarFilter", "carFilterDesc", "carFilterColName", "carFilterColClass",
             "carFilterTitle", "mappingPageLabel", "mappingPrevPage", "mappingNextPage"]


def _all_lang_text(lang: str) -> str:
    """TRANSLATIONS + EXTRA blocks of one language."""
    parts = []
    for m in re.finditer(r"^  %s: \{" % lang, I18N_JS, re.M):
        nxt = re.search(r"^  \},?\s*$", I18N_JS[m.end():], re.M)
        assert nxt
        parts.append(I18N_JS[m.end():m.end() + nxt.start()])
    assert parts
    return "\n".join(parts)


@pytest.fixture(scope="module")
def all_langs():
    return {"it": _all_lang_text("it"), "en": _all_lang_text("en")}


def _nonempty_in(text: str, key: str) -> bool:
    pat = r"(?:^|[,{])\s*%s:\s*(\"[^\"]+\"|'[^']+'|`[^`]+`|\([^)]*\)\s*=>)" % key
    return bool(re.search(pat, text, re.M))


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("key", VIEW_KEYS)
def test_view_i18n_keys_nonempty(all_langs, lang, key):
    assert _nonempty_in(all_langs[lang], key), (lang, key)


def test_nav_carfilter_before_mapping_in_bottom_nav():
    m = re.search(r"navBottom\.innerHTML\s*=(.*?)bindNavItemClicks\(navBottom\)", APP_JS, re.S)
    assert m
    views = re.findall(r'view:\s*"(\w+)"', m.group(1))
    assert views == ["carfilter", "mapping", "settings"]
    assert "icon: ICONS.navCarFilter" in m.group(1) and 't("navCarFilter")' in m.group(1)
    assert re.search(r"^  navCarFilter: `<svg", APP_JS, re.M)


def test_view_container_in_index_html_before_mapping():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert 'id="view-carfilter"' in html
    assert html.index('id="view-carfilter"') < html.index('id="view-mapping"')
    assert 'id="nav-bottom"' in html


def test_view_wiring_render_and_go_to_view():
    assert "renderCarFilterView();" in _function_source("render")
    go = _function_source("goToView")
    m = re.search(r'state\.view === "carfilter"\)\s*\{(.*?)\n  \}', go, re.S)
    assert m, "goToView has no carfilter branch"
    assert "refreshCarFilter()" in m.group(1) and "renderCarFilterView()" in m.group(1)
    assert "view-${state.view}" in _function_source("applyActiveView")
    view = _function_source("renderCarFilterView")
    assert 'getElementById("view-carfilter")' in view
    assert 'id="car-filter-section"' in view and "renderCarFilterSection()" in view
    assert "carFilterTitle" in view and "carFilterDesc" in view


def test_mapping_view_has_no_car_filter_code():
    src = _function_source("renderMappingView")
    assert not re.search(r"car-?filter", src, re.I)
    assert "CarFilter" not in _function_source("refreshMappings")
    go = _function_source("goToView")
    m = re.search(r'state\.view === "mapping"\)\s*\{(.*?)\n  \}', go, re.S)
    assert m and "CarFilter" not in m.group(1)


def test_pagination_constants_and_ids():
    assert "const MAPPING_PAGE_SIZE = 8;" in APP_JS
    assert re.search(r"^\s*carFilterPage: 0,", APP_JS, re.M)
    vm = _function_source("getCarFilterViewModel")
    assert "MAPPING_PAGE_SIZE" in vm and "state.carFilterPage" in vm and "pageCount" in vm
    lst = _function_source("renderCarFilterList")
    for dom_id in ["car-filter-prev-page", "car-filter-next-page"]:
        assert f'id="{dom_id}"' in lst and f'getElementById("{dom_id}")' in lst
    assert 'getElementById("car-filter-groups")' in lst
    assert 'id="car-filter-groups"' in _function_source("renderCarFilterSection")
    for k in ["mappingPageLabel", "mappingPrevPage", "mappingNextPage"]:
        assert f'"{k}"' in lst, k
    assert "state.carFilterPage = 0" in _function_source("renderCarFilterSection")


def test_save_car_filter_robustness_markers_kept():
    fn = _function_source("saveCarFilter")
    for marker in ["carFilterConfirmed", "carFilterSaveSeq", "carFilterSaveError", "catch",
                   "renderCarFilterSection()"]:
        assert marker in fn, marker
    assert "if (!state.carFilter.loaded) return" in _function_source("changeCarFilter")
    assert "loaded: true" in _function_source("refreshCarFilter")
    assert "await carFilterSaveChain" in _function_source("refreshCarFilter")


def test_all_literal_i18n_keys_used_in_app_exist_in_both_languages(all_langs):
    used = set(re.findall(r'\bt(?:Fn)?\(\s*"(\w+)"', APP_JS))
    assert used
    for lang, text in all_langs.items():
        defined = set(re.findall(r"(?:^|[,{])\s*(\w+):", text, re.M))
        missing = sorted(k for k in used if k not in defined)
        assert not missing, (lang, missing)
