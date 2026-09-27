/**
 * Chart-panel regression test for the portfolio pages.
 *
 * WHY THIS EXISTS
 * ---------------
 * The Board page and the Overview page both render two independent line charts
 * (inception + last 12 months) from two independent series. Both pages contained
 * the same bug:
 *
 *     if (!data.seriesAll || !data.series1y) return;   // blanks BOTH charts
 *
 * The 1-year series is null whenever no position entered the portfolio in the
 * last 365 days, which is normal for a long-held portfolio. So a single missing
 * series silently removed BOTH charts. It looked like a data problem, not a
 * rendering problem, and it was fixed first on one page and then the other.
 *
 * The invariant asserted here is the one that was violated:
 *
 *     every series that is present gets its own chart, independently,
 *     and every series that is absent gets a visible placeholder.
 *
 * USAGE
 * -----
 * Requires jsdom and a RENDERED page (these templates contain Jinja):
 *
 *     npm install jsdom
 *     curl -s -b cookies.txt http://127.0.0.1:5001/analyst/overview > /tmp/overview.html
 *     curl -s -b cookies.txt http://127.0.0.1:5001/admin/board      > /tmp/board.html
 *     node tests/js/chart_panels.test.js /tmp/overview.html /tmp/board.html
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
        } catch (err) {
            /* try next */
        }
    }
    console.error('jsdom not found. Install it with:  npm install jsdom');
    process.exit(2);
}

const { JSDOM } = loadJsdom();

const CANVAS_IDS = ['inceptionChart', 'oneyearChart'];

function render(html) {
    const dom = new JSDOM(html, {
        runScripts: 'outside-only',
        pretendToBeVisual: true,
        url: 'http://localhost/',
    });
    const { window } = dom;
    const created = [];

    window.HTMLCanvasElement.prototype.getContext = function () {
        return { canvas: this };
    };
    window.Chart = class Chart {
        constructor(ctx, config) {
            this.ctx = ctx;
            this.config = config;
            created.push(this);
        }
        destroy() {}
        update() {}
    };
    window.bootstrap = {
        Modal: class { constructor() {} show() {} hide() {} },
        Tooltip: class { constructor() {} },
    };
    window.fetch = () => Promise.resolve({ json: () => Promise.resolve({}), ok: true });
    window.EventSource = class { constructor() {} close() {} };

    // A real page runs all inline blocks in one global scope; eval() keeps
    // top-level const/let eval-scoped, so concat and append a probe.
    const source = [...window.document.querySelectorAll('script:not([src])')]
        .map((s) => s.textContent)
        .join('\n;\n');

    window.eval(`${source}
;window.__probe = (function () {
    var container = (typeof portfolioData !== 'undefined') ? portfolioData
                  : (typeof approvedData !== 'undefined') ? approvedData
                  : (typeof purchasedData !== 'undefined') ? purchasedData
                  : null;
    return {
        container: container,
        seriesAll: container ? container.seriesAll
                             : (typeof seriesAllData !== 'undefined' ? seriesAllData : null),
        series1y: container ? container.series1y
                            : (typeof series1yData !== 'undefined' ? series1yData : null)
    };
})();`);

    window.document.dispatchEvent(new window.Event('DOMContentLoaded', { bubbles: true }));
    return { window, created };
}

function noteShown(window, id) {
    const note = window.document.getElementById(id + 'Empty');
    return !!note && note.style.display !== 'none';
}

function canvasHidden(window, id) {
    const canvas = window.document.getElementById(id);
    return !canvas || canvas.style.display === 'none';
}

let failures = 0;

function check(label, actual, expected) {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    console.log(`    ${ok ? 'PASS' : 'FAIL'}  ${label}` +
        (ok ? '' : `  (expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)})`));
    if (!ok) failures++;
}

function hasSeries(series) {
    return !!series && Array.isArray(series.dates) && series.dates.length > 0;
}

function testPage(file) {
    console.log(`\n${file}`);
    const html = fs.readFileSync(file, 'utf8');
    const { window, created } = render(html);
    const probe = window.__probe;

    if (!probe || (probe.seriesAll === null && probe.series1y === null)) {
        console.log('    (no series data found on this page, skipping)');
        return;
    }

    const present = CANVAS_IDS.filter((id, i) =>
        hasSeries(i === 0 ? probe.seriesAll : probe.series1y));
    const absent = CANVAS_IDS.filter((id) => !present.includes(id));

    console.log(`    series present: ${present.join(', ') || 'none'}` +
        ` | absent: ${absent.join(', ') || 'none'}`);

    // The core invariant that was violated: one chart per present series.
    check('one chart drawn per present series', created.length, present.length);

    for (const id of present) {
        check(`${id} canvas visible`, canvasHidden(window, id), false);
    }
    for (const id of absent) {
        check(`${id} canvas hidden`, canvasHidden(window, id), true);
        check(`${id} placeholder shown`, noteShown(window, id), true);
    }
}

const files = process.argv.slice(2);
if (files.length === 0) {
    console.error('usage: node tests/js/chart_panels.test.js <rendered.html> [...]');
    process.exit(2);
}

files.forEach(testPage);

console.log(`\n${failures === 0 ? 'ALL CHECKS PASSED' : `FAILED (${failures} check(s))`}`);
process.exit(failures === 0 ? 0 : 1);
