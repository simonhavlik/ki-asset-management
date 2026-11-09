(function () {
  'use strict';

  const composer = document.getElementById('new-proposal');
  document.querySelectorAll('a[href="#new-proposal"]').forEach(link => {
    link.addEventListener('click', () => {
      if (composer) composer.open = true;
      if (link.dataset.selectAnalysis) {
        document.getElementById('proposal-analysis').value = link.dataset.selectAnalysis;
      }
    });
  });

  const sortDate = document.querySelector('[data-sort-analysis-date]');
  if (sortDate) {
    sortDate.addEventListener('click', () => {
      const heading = sortDate.closest('th');
      const body = heading.closest('table').tBodies[0];
      const descending = heading.getAttribute('aria-sort') !== 'descending';
      const rows = Array.from(body.rows, row => ({
        row,
        date: row.querySelector('time[datetime]')?.dateTime,
      })).filter(entry => entry.date);
      if (!rows.length) return;
      const direction = descending ? -1 : 1;
      rows.sort((a, b) => a.date.localeCompare(b.date) * direction);
      heading.setAttribute('aria-sort', descending ? 'descending' : 'ascending');
      rows.forEach(({row}) => body.append(row));
    });
  }

  const list = document.querySelector('[data-ballot-list]');
  if (!list) return;

  list.addEventListener('click', event => {
    const toggle = event.target.closest('[data-edit-toggle]');
    if (toggle) {
      const editor = document.getElementById(toggle.getAttribute('aria-controls'));
      editor.hidden = !editor.hidden;
      toggle.setAttribute('aria-expanded', String(!editor.hidden));
      if (!editor.hidden) editor.elements.rationale.focus();
      return;
    }
    const cancel = event.target.closest('[data-edit-cancel]');
    if (cancel) {
      const editor = cancel.form;
      const button = editor.closest('[data-proposal]').querySelector('[data-edit-toggle]');
      editor.reset();
      editor.hidden = true;
      button.setAttribute('aria-expanded', 'false');
      button.focus();
    }
  });

  function isInteracting() {
    return document.hidden || list.contains(document.activeElement)
      || list.querySelector('[data-edit-toggle][aria-expanded="true"]');
  }

  let busy = false;
  async function refresh() {
    if (busy || isInteracting()) return;
    busy = true;
    try {
      const response = await fetch(list.dataset.liveUrl, {credentials: 'same-origin', cache: 'no-store'});
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const data = await response.json();
      if (isInteracting()) return;
      list.innerHTML = data.html;
      document.querySelector('[data-proposal-total]').textContent = data.total;
      const next = document.querySelector('[data-next-page]');
      if (next) next.hidden = data.total <= Number(list.dataset.page) * 25;
      if (window.LANG) window.LANG.apply();
      document.querySelector('[data-live-state]').textContent = '';
    } catch (error) {
      const lang = window.LANG;
      document.querySelector('[data-live-state]').textContent = lang
        ? lang.texts[lang.current]['voting.refresh_error']
        : 'Automatic refresh unavailable; reload the page.';
    } finally {
      busy = false;
    }
  }

  setInterval(refresh, 30000);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refresh();
  });
})();
