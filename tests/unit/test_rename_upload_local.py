"""Dual mode rename: 'Upload + Locale' (it) / 'Upload + Local' (en)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
I18N = ROOT / "src" / "gui" / "web" / "i18n.js"
OLD_NAME = "Master + Loc"


def _dual_titles():
    return re.findall(r'modeDualTitle:\s*"([^"]*)"', I18N.read_text(encoding="utf-8"))


def test_i18n_dual_titles():
    # Order in file: it first, then en.
    assert _dual_titles() == ["Upload + Locale", "Upload + Local"]


def test_old_name_gone():
    files = [p for p in (ROOT / "src").rglob("*") if p.is_file() and p.suffix not in (".pyc", ".png", ".ico", ".woff", ".woff2")]
    files += [ROOT / "readme.md", ROOT / "readme.it.md"]
    offenders = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if OLD_NAME in text:
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == []


def _slug(heading):
    s = heading.strip().lower()
    s = re.sub(r"[`*_~]", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[^\w\s-]", "", s)
    return s.replace(" ", "-")


def _slugs(text):
    slugs, seen, in_code = set(), {}, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        m = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m and not in_code:
            base = _slug(m.group(1))
            n = seen.get(base, 0)
            seen[base] = n + 1
            slugs.add(base if n == 0 else f"{base}-{n}")
    return slugs


import pytest


@pytest.mark.parametrize("name", ["readme.md", "readme.it.md"])
def test_readme_anchors_resolve(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    slugs = _slugs(text)
    anchors = re.findall(r"\]\(#([^)\s]+)\)", text)
    broken = [a for a in anchors if a.lower() not in slugs]
    assert broken == []
