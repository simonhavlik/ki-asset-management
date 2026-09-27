#!/usr/bin/env python
"""
Translation coverage audit.

Reports, per template, which translatable strings still have no Czech, and which
dictionary entries are no longer referenced anywhere.

    venv/bin/python scripts/i18n_audit.py            # report
    venv/bin/python scripts/i18n_audit.py --strict   # non-zero exit if untranslated

The English text always stays in the template, so an untranslated key degrades to
English rather than breaking the page. This script is how you find those.

HOW TRANSLATIONS WORK
---------------------
  * A template marks a string with a key:
        <h2 data-i18n="about.mission">Our Mission</h2>
        <a data-i18n-html="nav.board"><i class="bi bi-clipboard"></i> Board</a>
  * The dictionary is app/static/js/i18n.js  ->  { "en": {...}, "cs": {...} }
  * data-i18n       replaces the element textContent, so the element must contain
                    TEXT ONLY. If it contains an icon, translating it deletes the
                    icon.
  * data-i18n-html  replaces innerHTML, so the value must carry the markup
                    (icons, <strong>, links) along with the words.
  * -placeholder, -title, -aria-label, -value target those attributes.
  * window.LANG lives ONLY in static/js/i18n.js. Do not define it anywhere else:
    a second definition silently replaced the object holding the strings and the
    language switch did nothing.

See docs/development/i18n.md for the full workflow.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
I18N_JS = ROOT / "app" / "static" / "js" / "i18n.js"

# Attributes that reference a translation key.
KEY_ATTRS = (
    "data-i18n", "data-i18n-html", "data-i18n-placeholder",
    "data-i18n-title", "data-i18n-aria-label", "data-i18n-value",
)
KEY_RE = re.compile(r'\b(' + "|".join(KEY_ATTRS) + r')="([^"]+)"')


def load_texts() -> dict:
    """Parse the TEXTS object out of i18n.js."""
    source = I18N_JS.read_text(encoding="utf-8")
    start = source.index("{", source.index("var TEXTS = "))
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
    raise SystemExit("could not parse TEXTS from i18n.js")


def template_keys() -> dict:
    """{relative template path: {key, ...}} for every marked string."""
    found = {}
    for path in sorted(TEMPLATES.rglob("*.html")):
        keys = set()
        for _attr, key in KEY_RE.findall(path.read_text(encoding="utf-8")):
            keys.add(key)
        if keys:
            found[str(path.relative_to(TEMPLATES))] = keys
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero when a template uses an unknown key")
    parser.add_argument("--show-missing", action="store_true",
                        help="list every untranslated key")
    args = parser.parse_args()

    texts = load_texts()
    en, cs = texts["en"], texts["cs"]
    per_template = template_keys()

    print(f"dictionary: {len(en)} English keys, {len(cs)} Czech keys "
          f"({len(cs) / len(en) * 100:.0f}% translated)\n" if en else "dictionary is empty\n")

    unknown, untranslated = [], []
    print(f"{'template':38s} {'keys':>5s} {'czech':>6s}  status")
    print("-" * 68)
    for rel, keys in sorted(per_template.items()):
        missing_keys = sorted(k for k in keys if k not in en)
        no_czech = sorted(k for k in keys if k in en and k not in cs)
        unknown.extend((rel, k) for k in missing_keys)
        untranslated.extend((rel, k) for k in no_czech)
        done = len(keys) - len(missing_keys) - len(no_czech)
        if missing_keys:
            status = f"UNKNOWN KEY(S): {', '.join(missing_keys[:2])}"
        elif no_czech:
            status = f"{len(no_czech)} untranslated"
        else:
            status = "complete"
        print(f"{rel:38s} {len(keys):>5d} {done:>6d}  {status}")

    used = {k for keys in per_template.values() for k in keys}
    stale = sorted(set(cs) - used)
    empty = sorted(k for k, v in cs.items() if not v.strip())

    print()
    if unknown:
        print(f"{len(unknown)} key(s) used by templates but MISSING from i18n.js:")
        for rel, key in unknown[:20]:
            print(f"   {rel}: {key}")
        print("   -> the element will keep showing its English text")
    else:
        print("no template references an unknown key")

    if untranslated:
        print(f"\n{len(untranslated)} marked string(s) still have no Czech:")
        shown = untranslated if args.show_missing else untranslated[:15]
        for rel, key in shown:
            print(f"   {rel}: {key}")
        if not args.show_missing and len(untranslated) > len(shown):
            print(f"   ... and {len(untranslated) - len(shown)} more "
                  f"(re-run with --show-missing)")
    else:
        print("every marked string has a Czech translation")

    if stale:
        print(f"\n{len(stale)} dictionary key(s) are no longer used by any template "
              f"(candidates for removal):")
        for key in stale[:15]:
            print(f"   {key}")
    if empty:
        print(f"\n{len(empty)} Czech value(s) are intentionally empty "
              f"(the word has no Czech equivalent): {', '.join(empty[:8])}")

    if unknown and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
