(function () {
  'use strict';

  const tr = (key, fallback) => window.LANG?.texts[window.LANG.current]?.[key] || fallback;

  document.querySelectorAll('[data-fundamentals]').forEach(panel => {
    panel.querySelectorAll('[data-metric-view]').forEach(button => {
      button.addEventListener('click', () => {
        panel.querySelectorAll('[data-metric-view]').forEach(item => {
          const selected = item === button;
          item.classList.toggle('active', selected);
          item.setAttribute('aria-pressed', String(selected));
        });
        panel.querySelectorAll('[data-metric-group]').forEach(cell => {
          cell.hidden = cell.dataset.metricGroup !== button.dataset.metricView;
        });
      });
    });

    panel.querySelector('[data-company-search]').addEventListener('input', event => {
      const needle = event.target.value.toLocaleLowerCase().trim();
      panel.querySelectorAll('[data-company-row]').forEach(row => {
        row.hidden = !row.dataset.search.includes(needle);
      });
    });
  });

  document.querySelectorAll('.results-table [data-sort-metric]').forEach(button => {
    button.addEventListener('click', () => {
      const header = button.closest('th');
      const table = header.closest('table');
      const body = table.tBodies[0];
      const current = header.getAttribute('aria-sort');
      const direction = current === 'ascending' ? 'descending'
        : current === 'descending' ? 'ascending'
        : table.dataset.sortDefault || 'ascending';
      const multiplier = direction === 'ascending' ? 1 : -1;
      const selector = '[data-metric="' + button.dataset.sortMetric + '"]';
      const rows = Array.from(body.rows, row => ({
        row,
        value: row.querySelector(selector)?.dataset.value,
      })).filter(entry => entry.value !== undefined);
      if (!rows.length) return;

      rows.sort((a, b) => {
        if (a.value === '') return b.value === '' ? 0 : 1;
        if (b.value === '') return -1;
        return (Number(a.value) - Number(b.value)) * multiplier;
      });
      table.querySelector('th[aria-sort]')?.removeAttribute('aria-sort');
      header.setAttribute('aria-sort', direction);
      rows.forEach(({row}) => body.append(row));
    });
  });

  const dialog = document.querySelector('[data-company-dialog]');
  if (dialog) {
    const content = dialog.querySelector('[data-company-content]');
    const title = dialog.querySelector('h2');
    const cache = new Map();
    let activeRequest;
    let trigger;

    dialog.addEventListener('close', () => {
      activeRequest?.abort();
      trigger?.focus();
    });

    content.addEventListener('click', event => {
      const button = event.target.closest('[data-detail-view]');
      if (!button) return;
      content.querySelectorAll('[data-detail-view]').forEach(item => {
        item.classList.toggle('active', item === button);
        item.setAttribute('aria-pressed', String(item === button));
      });
      content.querySelectorAll('[data-detail-group]').forEach(section => {
        section.hidden = section.dataset.detailGroup !== button.dataset.detailView;
      });
    });

    document.querySelectorAll('[data-details-url]').forEach(button => {
      button.addEventListener('click', async () => {
        trigger = button;
        const url = button.dataset.detailsUrl;
        title.textContent = button.querySelector('span').textContent;
        content.textContent = '…';
        content.setAttribute('aria-busy', 'true');
        dialog.showModal();
        activeRequest = new AbortController();
        const request = activeRequest;
        try {
          if (!cache.has(url)) {
            const response = await fetch(url, {credentials: 'same-origin', signal: request.signal});
            if (!response.ok) throw new Error('HTTP ' + response.status);
            cache.set(url, await response.text());
          }
          if (request.signal.aborted) return;
          content.innerHTML = cache.get(url);
          window.LANG?.apply();
        } catch (error) {
          if (!request.signal.aborted) {
            content.textContent = tr('results.detail_error', 'Unable to load saved statistics. Please try again.');
          }
        } finally {
          if (activeRequest === request) content.removeAttribute('aria-busy');
        }
      });
    });
  }

  const dashboardReturns = document.querySelector('[data-analyst-returns]');
  const dashboardCanvas = document.getElementById('dashboardReturns');
  if (dashboardReturns && dashboardCanvas && typeof Chart !== 'undefined') {
    const rows = JSON.parse(dashboardReturns.textContent);
    new Chart(dashboardCanvas, {
      type: 'bar',
      data: {
        labels: rows.map(row => row.ticker || row.name),
        datasets: [{
          data: rows.map(row => row.value),
          backgroundColor: rows.map(row => row.value >= 0 ? '#278957' : '#c55059'),
          borderRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        plugins: {
          legend: {display: false},
          tooltip: {callbacks: {
            title: items => rows[items[0].dataIndex].name + ' · ' + rows[items[0].dataIndex].date,
            label: item => item.parsed.y.toFixed(2) + '%',
          }},
        },
        scales: {
          x: {ticks: {autoSkip: true, maxTicksLimit: 12}},
          y: {ticks: {callback: value => value + '%'}},
        },
      },
    });
  }
})();
