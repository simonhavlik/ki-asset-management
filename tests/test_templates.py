"""
Template markup sanity checks.

These exist because a script that rewrote opening tags to add translation
attributes had an off-by-one: it replaced from the last character of the tag name
instead of from the '<'. The result was markup like

    << href="/analyst/" class="btn-hero-primary" data-i18n-html="btn.dashboard">">

which browsers render as literal text, so a button showed
"<<" plus a fragment of the tag. Nothing in the test suite noticed, because the
tests only checked that translation KEYS existed.

The checks here are cheap and catch that whole family of mistakes without a
browser.
"""

import pathlib
import re

import pytest

TEMPLATES = pathlib.Path(__file__).resolve().parent.parent / "app" / "templates"
ALL_TEMPLATES = sorted(TEMPLATES.rglob("*.html"))


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: p.name)
def test_no_double_angle_bracket(path):
    """'<<' only ever means mangled markup (there is no templating that emits it)."""
    text = read(path)
    for i, line in enumerate(text.splitlines(), start=1):
        assert "<<" not in line, f"{path.name}:{i} contains '<<': {line.strip()[:90]}"


@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: p.name)
def test_no_stray_quote_after_a_translation_marker(path):
    """A translation attribute must end its tag, not be followed by a dangling
    quote and another '>' (the signature of the broken rewrite)."""
    bad = re.findall(r'data-i18n(?:-[a-z-]+)?="[^"]*">"', read(path))
    assert not bad, f"{path.name}: stray quote after marker: {bad[:3]}"


@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: p.name)
def test_no_dangling_quote_before_closing_angle(path):
    """'data-i18n="key""' style duplication."""
    bad = re.findall(r'data-i18n(?:-[a-z-]+)?="[^"]+""', read(path))
    assert not bad, f"{path.name}: duplicated quote: {bad[:3]}"


@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: p.name)
def test_elements_using_data_i18n_contain_no_child_elements(path):
    """data-i18n replaces textContent, so an element using it must hold text only.
    If it also holds an icon, translating it deletes the icon - use data-i18n-html."""
    text = read(path)
    problems = []
    for m in re.finditer(r'<([a-zA-Z][a-zA-Z0-9]*)\b([^<>]*\bdata-i18n="[^"]+"[^<>]*)>', text):
        if "data-i18n-html" in m.group(2):
            continue
        tag = m.group(1)
        close = text.find("</%s>" % tag, m.end())
        if close == -1:
            continue
        inner = text[m.end():close]
        if re.search(r"<[a-zA-Z]", inner):
            problems.append((text[:m.start()].count("\n") + 1, " ".join(inner.split())[:60]))
    assert not problems, (
        f"{path.name}: these use data-i18n but contain child markup "
        f"(icons would be deleted when translated): {problems[:3]}"
    )


@pytest.mark.parametrize("tag", ["a", "div", "span", "button", "form", "li", "ul", "table"])
@pytest.mark.parametrize("path", ALL_TEMPLATES, ids=lambda p: p.name)
def test_tags_are_balanced(path, tag):
    """Catch a rewrite that consumed a tag name or dropped a closing tag.
    Jinja can legitimately open in one branch and close in another, so a small
    tolerance is allowed."""
    text = read(path)
    opens = len(re.findall(r"<%s\b" % tag, text))
    closes = len(re.findall(r"</%s>" % tag, text))
    assert abs(opens - closes) <= 2, (
        f"{path.name}: <{tag}> opened {opens}x but closed {closes}x"
    )
