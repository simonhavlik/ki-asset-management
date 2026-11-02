(function(){
  'use strict';
  document.querySelectorAll('[data-fundamentals]').forEach(panel=>{
    panel.querySelectorAll('[data-metric-view]').forEach(button=>button.addEventListener('click',()=>{
      panel.querySelectorAll('[data-metric-view]').forEach(item=>{const active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-pressed',String(active));});
      panel.querySelectorAll('[data-metric-group]').forEach(cell=>{cell.hidden=cell.dataset.metricGroup!==button.dataset.metricView;});
    }));
    panel.querySelector('[data-company-search]').addEventListener('input',event=>{
      const needle=event.target.value.toLocaleLowerCase().trim();
      panel.querySelectorAll('[data-company-row]').forEach(row=>{row.hidden=!row.dataset.search.includes(needle);const detail=row.nextElementSibling;detail.hidden=row.hidden||row.querySelector('[data-details-url]').getAttribute('aria-expanded')!=='true';});
    });
    panel.querySelectorAll('[data-sort-metric]').forEach(button=>button.addEventListener('click',()=>{
      const ascending=button.dataset.direction!=='asc';button.dataset.direction=ascending?'asc':'desc';
      const rows=Array.from(panel.querySelectorAll('[data-company-row]'));
      rows.sort((a,b)=>{const left=a.querySelector('[data-metric="'+button.dataset.sortMetric+'"]').dataset.value;const right=b.querySelector('[data-metric="'+button.dataset.sortMetric+'"]').dataset.value;if(left==='')return right===''?0:1;if(right==='')return -1;return (Number(left)-Number(right))*(ascending?1:-1);});
      rows.forEach(row=>{const detail=row.nextElementSibling;row.parentElement.append(row,detail);});
    }));
    panel.querySelectorAll('[data-details-url]').forEach(button=>button.addEventListener('click',async()=>{
      const detail=document.getElementById(button.getAttribute('aria-controls'));const open=button.getAttribute('aria-expanded')!=='true';button.setAttribute('aria-expanded',String(open));detail.hidden=!open;if(!open||detail.dataset.loaded)return;
      const content=detail.querySelector('[data-detail-content]');content.textContent='…';button.disabled=true;
      try{const response=await fetch(button.dataset.detailsUrl,{credentials:'same-origin'});if(!response.ok)throw new Error('HTTP '+response.status);content.innerHTML=await response.text();detail.dataset.loaded='true';if(window.LANG&&window.LANG.apply)window.LANG.apply();}
      catch(error){content.textContent=window.LANG&&window.LANG.texts?window.LANG.texts[window.LANG.current]['results.detail_error']:'Unable to load saved statistics. Please try again.';}
      finally{button.disabled=false;}
    }));
  });
})();
