(function () {
    document.querySelectorAll('[data-utc]').forEach(function (el) {
        var date = new Date(el.dataset.utc);
        if (!isNaN(date)) el.textContent = date.toLocaleString('cs-CZ', {timeZone: 'Europe/Prague', dateStyle: 'short', timeStyle: 'short'});
    });
    document.querySelectorAll('.schedule-card').forEach(function (form) {
        var frequency = form.querySelector('[name=frequency]');
        function update() { form.dataset.frequency = frequency.value; form.querySelector('.schedule-day').hidden = frequency.value !== 'weekly'; }
        frequency.addEventListener('change', update); update();
    });
})();
