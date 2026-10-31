(function () {
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    var bulk = document.getElementById('resolveAllTickers');
    var busy = false;
    function tr(key) { return window.LANG && window.LANG.texts[window.LANG.current][key] || key; }
    async function resolve(row) {
        var button = row.querySelector('.ticker-resolve');
        var status = row.querySelector('.ticker-ai-status');
        button.disabled = true; status.textContent = tr('ticker.working');
        try {
            var response = await fetch(row.dataset.resolveUrl, {method:'POST', headers:{'X-CSRFToken':csrf}});
            var result = await response.json();
            if (!response.ok || !result.success) throw new Error(result.error || tr('ticker.failed'));
            var other = result.is_other;
            var field = row.querySelector('[name=ticker_symbol]');
            field.value = result.ticker || ''; field.disabled = other;
            row.querySelector('.ticker-symbol-form button').disabled = other;
            row.querySelectorAll('.ticker-type button').forEach(function (el) {
                var active = (el.value === 'other') === other;
                el.classList.toggle('active', active); el.setAttribute('aria-pressed', String(active));
            });
            row.dataset.auto = '0';
            status.textContent = other ? tr('ticker.other') : result.ticker;
            document.getElementById('reloadTickerList').classList.remove('d-none');
        } catch (error) { status.textContent = tr('ticker.failed'); }
        finally { button.disabled = false; }
    }
    document.querySelectorAll('[data-company-row]').forEach(function (row) {
        row.querySelector('.ticker-resolve').addEventListener('click', function () { if (!busy) resolve(row); });
    });
    bulk.addEventListener('click', async function () {
        if (busy) return;
        var rows = Array.from(document.querySelectorAll('[data-company-row][data-auto="1"]'));
        busy = true; bulk.disabled = true;
        var status = document.getElementById('tickerBatchStatus');
        try {
            for (var i=0; i<rows.length; i++) {
                status.textContent = tr('ticker.working') + ' ' + (i+1) + ' / ' + rows.length;
                await resolve(rows[i]);
            }
            status.textContent = tr('ticker.finished') + ' ' + rows.length;
        } finally { busy = false; bulk.disabled = false; }
    });
})();
