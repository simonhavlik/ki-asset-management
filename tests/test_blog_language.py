"""SEO follows the language the analyst wrote in.

The editor's "Generate SEO" used to always return the English fields, even for
Czech articles. These pin the language detector that decides which generated
SEO set to use.
"""

from app.utils.blog_ai_utils import detect_language


def test_detects_czech_with_diacritics():
    assert detect_language("Analýza akcií společnosti ČEZ a výhled na rok 2026") == "cs"
    assert detect_language("<p>Toto je český článek o trzích a investicích.</p>") == "cs"


def test_detects_czech_without_many_diacritics():
    # short, accent-light but clearly Czech (stop-words)
    assert detect_language("Je to dobra akcie a trh se zmenil, ale ne pro vsechny") == "cs"


def test_detects_english():
    assert detect_language("An in-depth analysis of Apple stock and its valuation") == "en"
    assert detect_language("") == "en"
    assert detect_language(None) == "en"


def test_tags_and_html_are_stripped():
    assert detect_language("<h2>Výsledky</h2><p>Tržby rostou a zisk je vyšší.</p>") == "cs"
