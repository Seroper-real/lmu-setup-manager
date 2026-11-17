"""Static tests for the dual-mode GUI wiring (src/gui/web, readmes).

No JS runtime is available, so app.js / i18n.js are checked textually.
"""
import re
from pathlib import Path

import pytest

from core.config import VALID_MODES

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "src" / "gui" / "web"
APP_JS = (WEB / "app.js").read_text(encoding="utf-8")
I18N_JS = (WEB / "i18n.js").read_text(encoding="utf-8")

DUAL_KEYS = ["modeDualTitle", "dualDesc", "modeGeneralDualDesc", "uploadDualDesc"]
MODES = sorted(VALID_MODES)


def _lang_text(lang: str) -> str:
    """Concatenate the TRANSLATIONS and EXTRA blocks of one language."""
    parts: list[str] = []
    for m in re.finditer(r"^  %s: \{" % lang, I18N_JS, re.M):
        nxt = re.search(r"^  \},?\s*$", I18N_JS[m.end():], re.M)
        assert nxt, f"unterminated {lang} block"
        parts.append(I18N_JS[m.end():m.end() + nxt.start()])
    assert parts, f"no {lang} blocks"
    return "\n".join(parts)


@pytest.fixture(scope="module")
def langs() -> dict[str, str]:
    return {"it": _lang_text("it"), "en": _lang_text("en")}


def _map_literal(name: str) -> dict[str, str]:
    m = re.search(r"const %s = \{(.*?)\};" % name, APP_JS, re.S)
    assert m, f"{name} not found"
    return dict(re.findall(r"(\w+):\s*\"(\w+)\"", m.group(1)))


def _has_nonempty(block: str, key: str) -> bool:
    m = re.search(r"\b" + key + r":\s*([\"'`])(.*?)\1", block)
    return bool(m) and len(m.group(2).strip()) > 0


@pytest.mark.parametrize("name", ["MODE_TITLE_KEYS", "DOWNLOAD_MODE_DESC_KEYS", "UPLOAD_MODE_DESC_KEYS"])
def test_every_mode_has_entry(name):
    assert set(_map_literal(name)) == set(VALID_MODES)


@pytest.mark.parametrize("mode", MODES)
def test_mode_picker_has_card(mode):
    m = re.search(r"function renderModePickerCards\(\) \{(.*?)return modes", APP_JS, re.S)
    assert m
    assert re.search(r'key:\s*"%s"' % mode, m.group(1))


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("name", ["MODE_TITLE_KEYS", "DOWNLOAD_MODE_DESC_KEYS", "UPLOAD_MODE_DESC_KEYS"])
def test_mapped_keys_exist(langs, lang, name):
    for key in _map_literal(name).values():
        assert _has_nonempty(langs[lang], key), f"{key} missing/empty in {lang}"


@pytest.mark.parametrize("lang", ["it", "en"])
@pytest.mark.parametrize("key", DUAL_KEYS)
def test_dual_keys_present(langs, lang, key):
    assert _has_nonempty(langs[lang], key)


@pytest.mark.parametrize("readme", ["readme.md", "readme.it.md"])
def test_readme_lists_dual(readme):
    text = (ROOT / readme).read_text(encoding="utf-8")
    m = re.search(r"--mode \{([^}]*)\}", text)
    assert m
    assert "dual" in m.group(1).split(",")


def test_all_used_i18n_keys_exist_in_both_languages(langs):
    """Generic guard: every t("x")/tFn("x") literal in app.js exists in it and en."""
    used = set(re.findall(r"\b(?:t|tFn)\(\s*\"(\w+)\"", APP_JS))
    assert used
    missing = {
        lang: sorted(k for k in used if not re.search(r"\b%s:" % k, langs[lang]))
        for lang in langs
    }
    assert not missing["it"] and not missing["en"], missing
