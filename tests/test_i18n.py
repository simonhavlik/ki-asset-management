"""
Translation plumbing tests.

Guards the bug where js/app.js *also* defined window.LANG. app.js loads after
js/i18n.js, so it silently replaced the object holding the translation strings:
LANG.apply and LANG.texts became undefined and the EN/CS toggle did nothing at
all. Nothing failed loudly - the site just stayed English.

Runs without a browser or a server.
"""

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = ROOT / "app" / "static" / "js"
TEMPLATES = ROOT / "app" / "templates"
I18N_JS = STATIC / "i18n.js"

# Public templates that must carry translation keys.
PUBLIC_TEMPLATES = [
    "main/index.html", "main/about.html", "main/methodology.html",
    "main/wall.html", "main/privacy.html", "main/terms.html",
    "blog/index.html", "blog/post.html", "blog/author.html",
    "auth/login.html", "auth/register.html", "auth/forgot_password.html",
    "auth/reset_password.html", "auth/set_password.html", "auth/activate.html",
]


def load_texts() -> dict:
    """Pull the TEXTS object out of i18n.js."""
    source = I18N_JS.read_text(encoding="utf-8")
    start = source.index("var TEXTS = ")
    start = source.index("{", start)
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(source)):
        ch = source[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(source[start:i + 1])
    raise AssertionError("unbalanced braces in i18n.js")


def test_lang_is_defined_in_exactly_one_place():
    """The whole bug in one assertion."""
    definers = [p.name for p in STATIC.glob("*.js")
                if "window.LANG = {" in p.read_text(encoding="utf-8")]
    assert definers == ["i18n.js"], (
        f"window.LANG must only be defined in i18n.js, found in {definers}"
    )


def test_app_js_does_not_redefine_lang():
    app_js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "window.LANG = {" not in app_js
    assert "LANG.init()" not in app_js, "i18n.js owns initialisation now"


def test_base_template_loads_i18n_js():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "js/i18n.js" in base, "base.html must include i18n.js"
    assert "window.LANG = {" not in base, (
        "the inline LANG definition belongs in i18n.js, not base.html"
    )


def test_language_toggle_button_calls_toggle():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert "window.LANG.toggle()" in base
    assert 'id="lang-indicator"' in base


# Pages that are fully translated. Add to this list as coverage grows; the test
# then guarantees the page never regresses back to showing English in Czech mode.
FULLY_TRANSLATED = [
    "main/about.html", "main/wall.html", "main/privacy.html", "main/terms.html",
    "auth/login.html", "auth/register.html", "auth/forgot_password.html",
    "auth/reset_password.html", "auth/set_password.html", "auth/activate.html",
]


def test_czech_is_a_subset_of_english():
    texts = load_texts()
    extra = set(texts["cs"]) - set(texts["en"])
    assert not extra, f"Czech keys missing from English: {sorted(extra)[:5]}"


def test_coverage_report():
    """Not a correctness check: prints how much of the public UI is translated."""
    texts = load_texts()
    total, done = len(texts["en"]), len(texts["cs"])
    pct = done / total * 100 if total else 0
    print(f"\nCzech coverage: {done}/{total} keys ({pct:.0f}%)")
    assert done > 0


@pytest.mark.parametrize("rel", FULLY_TRANSLATED)
def test_fully_translated_pages_have_no_english_left(rel):
    path = TEMPLATES / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    texts = load_texts()
    keys = re.findall(r'data-i18n(?:-html)?="([^"]+)"', path.read_text(encoding="utf-8"))
    missing = sorted({k for k in keys if k not in texts["cs"]})
    assert not missing, f"{rel} still falls back to English for: {missing[:8]}"


def test_translation_values_are_strings():
    """Values may intentionally be empty (e.g. hero.only has no Czech equivalent),
    but they must be strings, not null/undefined leaking from the generator."""
    texts = load_texts()
    bad = [k for lang in ("en", "cs") for k, v in texts[lang].items()
           if not isinstance(v, str)]
    assert not bad, f"non-string translation values: {bad[:5]}"


@pytest.mark.parametrize("rel", PUBLIC_TEMPLATES)
def test_marked_keys_exist_in_the_dictionary(rel):
    """Every key a template uses must exist, otherwise the element silently
    keeps its English text in Czech mode."""
    path = TEMPLATES / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    keys = set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', path.read_text(encoding="utf-8")))
    texts = load_texts()
    missing = sorted(k for k in keys if k not in texts["en"])
    assert not missing, f"{rel} uses keys absent from i18n.js: {missing[:8]}"


@pytest.mark.parametrize("rel", PUBLIC_TEMPLATES)
def test_translated_keys_keep_their_markup(rel):
    """Czech must contain the same inline tags as English, otherwise the page
    loses bold text, icons or links when switched."""
    path = TEMPLATES / rel
    if not path.exists():
        pytest.skip(f"{rel} not present")
    texts = load_texts()
    tag = re.compile(r"</?[a-zA-Z][^<>]*?>")
    bad = []
    for key in set(re.findall(r'data-i18n(?:-html)?="([^"]+)"', path.read_text(encoding="utf-8"))):
        if key not in texts["cs"]:
            continue
        if sorted(tag.findall(texts["en"][key])) != sorted(tag.findall(texts["cs"][key])):
            bad.append(key)
    assert not bad, f"{rel}: Czech changed inline tags for {bad[:5]}"
