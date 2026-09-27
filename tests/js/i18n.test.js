/**
 * Language system + translation coverage, checked against a RENDERED page.
 *
 * WHY THIS EXISTS
 * ---------------
 * Three bugs in this area were invisible to the Python tests:
 *   1. js/app.js defined window.LANG a second time, replacing the object that
 *      held the dictionary, so the EN/CS toggle silently did nothing.
 *   2. Several elements used data-i18n (which replaces textContent) while
 *      containing an icon, so switching to Czech DELETED the icon.
 *   3. A bulk edit mangled opening tags into "<< href=..." which browsers render
 *      as literal text on the page.
 *
 * Only a real DOM can catch these. tests/js/chart_panels.test.js covers the
 * chart equivalent.
 *
 * USAGE (needs jsdom and a rendered page, because the templates contain Jinja)
 *   npm install jsdom
 *   for p in / /about /methodology /wall /privacy /terms /blog/ /auth/login; do
 *       f=$(echo "$p" | tr '/' '_')
 *       curl -s -b cookies.txt "http://127.0.0.1:5001$p" > "/tmp/page$f.html"
 *   done
 *   node tests/js/i18n.test.js /tmp/page_*.html
 *
 * Exit code 0 = all checks passed.
 */

'use strict';

const fs = require('fs');
const path = require('path');

function loadJsdom() {
    for (const candidate of ['jsdom', path.join(process.cwd(), 'node_modules', 'jsdom')]) {
        try {
            return require(candidate);
        } catch (err) { /* try next */ }
    }
    console.error('jsdom not found. Install it with:  npm install jsdom');
    process.exit(2);
}

const { JSDOM } = loadJsdom();
const I18N_JS = 'app/static/js/i18n.js';
const APP_JS = 'app/static/js/app.js';

let failures = 0;

function check(label, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    console.log(`    ${ok ? 'PASS' : 'FAIL'}  ${label}` +
        (ok ? '' : `  (expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)})`));
    if (!ok) failures++;
}

/** Boot a rendered page exactly like the browser does. */
function boot(html, { languages, savedLang } = {}) {
    const dom = new JSDOM(html, {
        url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true,
    });
    const w = dom.window;

    // Stubs for what jsdom does not implement.
    w.bootstrap = { Tooltip: class {}, Modal: class { show() {} hide() {} } };
    w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
    w.matchMedia = () => ({
        matches: false, addListener() {}, removeListener() {},
        addEventListener() {}, removeEventListener() {},
    });

    w.localStorage.clear();
    if (savedLang) w.localStorage.setItem('lang', savedLang);
    const langs = languages || ['en-US', 'en'];
    Object.defineProperty(w.navigator, 'languages', { value: langs, configurable: true });
    Object.defineProperty(w.navigator, 'language', { value: langs[0], configurable: true });

    // Script order as in the page: i18n.js in <head>, app.js at the end of body.
    w.eval(fs.readFileSync(I18N_JS, 'utf8'));
    try { w.eval(fs.readFileSync(APP_JS, 'utf8')); } catch (err) { /* unrelated app.js features */ }

    // The head script runs while readyState is "loading", so init() is wired to
    // DOMContentLoaded. Fire it, as a browser would.
    w.document.dispatchEvent(new w.Event('DOMContentLoaded', { bubbles: true }));
    return w;
}

function normalise(s) {
    return s.replace(/\u00a0/g, ' ').replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&').replace(/\s+/g, ' ').trim();
}

/**
 * Compare structure and words, ignoring attributes.
 *
 * app.js decorates links at runtime (it adds data-cursor-hover="true" for the
 * custom cursor), so innerHTML legitimately differs from the dictionary by
 * attributes. Tag names, nesting and text must still match exactly.
 */
function canonical(s) {
    return normalise(s
        .replace(/<([a-zA-Z][a-zA-Z0-9]*)\b[^<>]*>/g, '<$1>')
        .replace(/<\/([a-zA-Z][a-zA-Z0-9]*)\s*>/g, '</$1>'));
}

function markedElements(w) {
    return [...w.document.querySelectorAll('[data-i18n],[data-i18n-html]')];
}

const files = process.argv.slice(2);
if (files.length === 0) {
    console.error('usage: node tests/js/i18n.test.js <rendered.html> [...]');
    process.exit(2);
}

// ---------------------------------------------------------------- global ---
console.log('Language system');
{
    const w = boot(fs.readFileSync(files[0], 'utf8'));

    check('only i18n.js owns window.LANG (app.js did not replace it)',
        [typeof w.LANG.texts, typeof w.LANG.apply], ['object', 'function']);

    const el = w.document.querySelector('[data-i18n]');
    if (el) {
        const key = el.getAttribute('data-i18n');
        w.LANG.set('en');
        check(`${key} shows English`, normalise(el.textContent), normalise(w.I18N.en[key]));
        w.LANG.set('cs');
        check(`${key} shows Czech`, normalise(el.textContent), normalise(w.I18N.cs[key]));
        check('<html lang> updated', w.document.documentElement.getAttribute('lang'), 'cs');
    }

    const cs = boot(fs.readFileSync(files[0], 'utf8'), { languages: ['cs-CZ', 'en'] });
    check('cs-CZ browser auto-selects Czech', cs.LANG.current, 'cs');

    const de = boot(fs.readFileSync(files[0], 'utf8'), { languages: ['de-DE'] });
    check('de-DE browser stays English', de.LANG.current, 'en');

    const override = boot(fs.readFileSync(files[0], 'utf8'),
        { languages: ['cs-CZ'], savedLang: 'en' });
    check('a saved choice beats the browser', override.LANG.current, 'en');
}

// ------------------------------------------------------- per page checks ---
for (const file of files) {
    console.log(`\n${file}`);
    const html = fs.readFileSync(file, 'utf8');

    check('no mangled "<" doubled markup in the source',
        (html.match(/<</g) || []).length, 0);

    for (const lang of ['en', 'cs']) {
        const w = boot(html, { savedLang: lang });
        const marked = markedElements(w);

        const missing = marked
            .map((el) => el.getAttribute('data-i18n') || el.getAttribute('data-i18n-html'))
            .filter((k) => !Object.prototype.hasOwnProperty.call(w.I18N.cs, k));
        check(`[${lang}] every marked string has a Czech translation`, missing.length, 0);

        const mismatched = marked.filter((el) => {
            const key = el.getAttribute('data-i18n') || el.getAttribute('data-i18n-html');
            const value = w.I18N[lang][key];
            if (value === undefined) return false;
            const raw = el.getAttribute('data-i18n-html') ? el.innerHTML : el.textContent;
            return canonical(raw) !== canonical(value);
        }).map((el) => el.getAttribute('data-i18n') || el.getAttribute('data-i18n-html'));
        check(`[${lang}] rendered text matches the dictionary`,
            mismatched.slice(0, 3), []);

        // Mangled markup renders as literal text containing "<".
        const stray = [];
        const walk = w.document.createTreeWalker(w.document.body, w.NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walk.nextNode())) {
            // Skip <script>/<style> contents: they are text nodes too, and JS
            // comments and CSS legitimately contain "<".
            const parent = node.parentElement && node.parentElement.tagName;
            if (parent === 'SCRIPT' || parent === 'STYLE') continue;
            if (node.nodeValue.includes('<')) stray.push(node.nodeValue.trim().slice(0, 60));
        }
        check(`[${lang}] no literal "<" in visible text`, stray.slice(0, 2), []);
    }
}

console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : `FAILED (${failures} check(s))`}`);
process.exit(failures === 0 ? 0 : 1);
