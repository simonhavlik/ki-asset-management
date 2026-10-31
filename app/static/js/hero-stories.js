/* Three opening views. All numbers and process text are server-rendered. */
(function () {
    'use strict';
    function initialize() {
    var root = document.getElementById('heroStories');
    if (!root) return;
    var scenes = Array.from(root.querySelectorAll('.hero-scene'));
    var tabs = Array.from(root.querySelectorAll('[data-scene]'));
    var stages = Array.from(root.querySelectorAll('[data-process-step]'));
    var details = Array.from(root.querySelectorAll('[data-phase-detail]'));
    var pause = document.getElementById('heroStoryPause');
    var canvas = document.getElementById('heroParticles');
    var ctx = canvas && canvas.getContext('2d');
    var reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    var durations = [12000, 9000, 32000];
    var current = 0, phase = 0, elapsed = 0, processElapsed = 0;
    var paused = false, hovered = false, focused = false, visible = true;
    var manualPhase = false, frameId = null, previous = 0, lastPaint = 0, lastProgress = 0;
    var width = 1, height = 1, sourceX = 90, sourceYs = [];

    function canAnimate() {
        return visible && !document.hidden && !paused && !reduced.matches &&
            !document.body.classList.contains('motion-paused');
    }

    function selectPhase(index) {
        phase = index;
        scenes[2].dataset.phase = String(index);
        stages.forEach(function (button, i) { button.setAttribute('aria-pressed', String(i === index)); });
        details.forEach(function (detail, i) {
            detail.hidden = i !== index;
            detail.classList.toggle('is-active', i === index);
        });
    }

    function draw(time) {
        if (!ctx) return;
        ctx.clearRect(0, 0, width, height);
        var start = sourceX;
        var activeY = sourceYs[phase] || height * (phase + .5) / 4;
        var glow = ctx.createRadialGradient(start, activeY, 1, start, activeY, 120);
        glow.addColorStop(0, 'rgba(26,156,94,.12)');
        glow.addColorStop(1, 'rgba(26,156,94,0)');
        ctx.fillStyle = glow;
        ctx.fillRect(0, 0, width, height);
        ctx.lineWidth = 1;
        for (var lane = 0; lane < 4; lane++) {
            var sourceY = sourceYs[lane] || height * (lane + .5) / 4;
            ctx.strokeStyle = lane === phase ? 'rgba(26,156,94,.22)' : 'rgba(26,156,94,.06)';
            ctx.beginPath();
            ctx.moveTo(start, sourceY);
            ctx.bezierCurveTo(width * .42, sourceY, width * .65, height / 2, width - 10, height / 2);
            ctx.stroke();
        }
        var count = width < 500 ? 140 : 300;
        for (var i = 0; i < count; i++) {
            var progress = (i / count + time * (.000025 + (i % 9) * .000002)) % 1;
            var originY = sourceYs[i % 4] || height * ((i % 4) + .5) / 4;
            var blend = progress * progress * (3 - 2 * progress);
            var px = start + progress * (width - start);
            var py = originY + (height / 2 - originY) * blend + Math.sin(progress * Math.PI) * ((i % 11) - 5) * 3;
            ctx.fillStyle = 'rgba(26,156,94,' + ((i % 4 === phase ? .3 : .08) + (i % 5) * .04) + ')';
            ctx.beginPath();
            ctx.arc(px, py, .65 + (i % 4) * .35, 0, Math.PI * 2);
            ctx.fill();
        }
        // A quieter field gives depth without competing with the real labels.
        for (var k = 0; k < (width < 500 ? 45 : 90); k++) {
            var dx = (k * 47.13 + time * .003 * (1 + k % 3)) % width;
            var dy = 12 + (k * 23.71) % (height - 20);
            ctx.fillStyle = 'rgba(26,156,94,.13)';
            ctx.fillRect(dx, dy, 1.4, 1.4);
        }
    }

    function resize() {
        if (!canvas || !ctx) return;
        var bounds = canvas.getBoundingClientRect();
        width = Math.max(1, bounds.width);
        height = Math.max(24, bounds.height);
        sourceX = stages[0].getBoundingClientRect().right - bounds.left;
        sourceYs = stages.map(function (stage) {
            var rect = stage.getBoundingClientRect();
            return rect.top + rect.height / 2 - bounds.top;
        });
        var scale = Math.min(window.devicePixelRatio || 1, 1.5);
        canvas.width = Math.round(width * scale);
        canvas.height = Math.round(height * scale);
        ctx.setTransform(scale, 0, 0, scale, 0, 0);
        if (current === 2) draw(0);
    }

    function show(index) {
        current = (index + scenes.length) % scenes.length;
        elapsed = 0;
        processElapsed = 0;
        manualPhase = false;
        scenes.forEach(function (scene, i) {
            scene.classList.toggle('is-active', i === current);
            scene.setAttribute('aria-hidden', String(i !== current));
            scene.inert = i !== current;
        });
        var photo = scenes[1].querySelector('[data-src]');
        if (current === 1 && photo && !photo.getAttribute('src')) {
            photo.addEventListener('load', function () { photo.classList.add('is-loaded'); }, {once: true});
            photo.srcset = photo.dataset.srcset;
            photo.src = photo.dataset.src;
        }
        tabs.forEach(function (tab, i) {
            tab.classList.toggle('is-active', i === current);
            tab.setAttribute('aria-selected', String(i === current));
            tab.tabIndex = i === current ? 0 : -1;
            tab.style.setProperty('--scene-progress', '0');
        });
        selectPhase(0);
        if (current === 2) { resize(); draw(0); }
    }

    function frame(time) {
        frameId = null;
        if (!canAnimate()) { previous = 0; return; }
        var delta = previous ? Math.min(time - previous, 100) : 0;
        previous = time;
        if (!hovered && !focused) elapsed += delta;
        if (elapsed >= durations[current]) show(current + 1);
        if (time - lastProgress >= 100) {
            tabs[current].style.setProperty('--scene-progress', String(elapsed / durations[current]));
            lastProgress = time;
        }
        if (current === 2) {
            if (!hovered && !focused) processElapsed += delta;
            var nextPhase = Math.floor(processElapsed / 7000) % 4;
            if (!manualPhase && nextPhase !== phase) selectPhase(nextPhase);
            if (time - lastPaint >= 32) { draw(time); lastPaint = time; }
        }
        frameId = requestAnimationFrame(frame);
    }

    function sync() {
        if (frameId !== null) cancelAnimationFrame(frameId);
        frameId = null;
        previous = 0;
        root.dataset.motion = canAnimate() ? 'running' : 'paused';
        if (canAnimate()) frameId = requestAnimationFrame(frame);
    }

    tabs.forEach(function (tab, index) {
        tab.addEventListener('click', function () { show(index); sync(); });
        tab.addEventListener('keydown', function (event) {
            var next;
            if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
            if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
            if (event.key === 'Home') next = 0;
            if (event.key === 'End') next = tabs.length - 1;
            if (next === undefined) return;
            event.preventDefault();
            show(next);
            tabs[next].focus();
            sync();
        });
    });
    stages.forEach(function (stage, index) {
        stage.addEventListener('click', function () { manualPhase = true; selectPhase(index); draw(processElapsed); });
    });
    pause.addEventListener('click', function () {
        paused = !paused;
        pause.setAttribute('aria-pressed', String(paused));
        var key = paused ? 'hero.story.resume' : 'hero.story.pause';
        pause.setAttribute('data-i18n-aria-label', key);
        var label = window.LANG && window.LANG.texts[window.LANG.current][key];
        pause.setAttribute('aria-label', label || (paused ? 'Resume animation' : 'Pause animation'));
        pause.querySelector('i').className = paused ? 'bi bi-play' : 'bi bi-pause';
        sync();
    });
    root.addEventListener('pointerenter', function () { hovered = true; });
    root.addEventListener('pointerleave', function () { hovered = false; });
    root.addEventListener('focusin', function () { focused = true; });
    root.addEventListener('focusout', function () { focused = root.contains(document.activeElement); });
    document.addEventListener('visibilitychange', sync);
    reduced.addEventListener('change', sync);
    new MutationObserver(sync).observe(document.body, {attributes: true, attributeFilter: ['class']});
    if (window.IntersectionObserver) new IntersectionObserver(function (entries) {
        visible = entries[0].isIntersecting;
        sync();
    }, {threshold: .1}).observe(root);
    if (window.ResizeObserver) new ResizeObserver(resize).observe(canvas);
    else window.addEventListener('resize', resize);
    resize();
    show(0);
    sync();
    }
    // Let the server-rendered portfolio paint before setting up optional motion.
    requestAnimationFrame(function () { requestAnimationFrame(initialize); });
})();
