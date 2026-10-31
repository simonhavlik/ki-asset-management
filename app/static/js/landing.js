/* Decorative motion is optional, stops offscreen, and never fetches data. */
(function () {
    var header = document.querySelector('.navbar');
    if (!header) return;
    function measureHeader() {
        document.body.style.setProperty('--ki-header-height', Math.ceil(header.getBoundingClientRect().height) + 'px');
    }
    measureHeader();
    if (window.ResizeObserver) new ResizeObserver(measureHeader).observe(header);
    else window.addEventListener('resize', measureHeader);
})();

(function () {
    var button = document.getElementById('kiMotion');
    if (!button) return;
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    var paused = reduced.matches;
    try { paused = paused || localStorage.getItem('ki-motion') === 'paused'; } catch (_) {}
    function apply() {
        document.body.classList.toggle('motion-paused', paused || document.hidden);
        button.setAttribute('aria-pressed', String(paused));
        button.setAttribute('data-i18n', paused ? 'polish.motion_resume' : 'polish.motion');
        if (window.LANG) window.LANG.apply();
    }
    button.addEventListener('click', function () {
        paused = !paused;
        try { localStorage.setItem('ki-motion', paused ? 'paused' : 'on'); } catch (_) {}
        apply();
    });
    document.addEventListener('visibilitychange', apply);
    reduced.addEventListener('change', function (e) { if (e.matches) { paused = true; apply(); } });
    apply();
})();
