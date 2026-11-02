(function(){'use strict';
  const composer=document.getElementById('new-proposal');
  document.querySelectorAll('a[href="#new-proposal"]').forEach(link=>link.addEventListener('click',()=>{if(composer)composer.open=true;if(link.dataset.selectAnalysis)document.getElementById('proposal-analysis').value=link.dataset.selectAnalysis;}));
  const list=document.querySelector('[data-ballot-list]');if(!list)return;
  let busy=false;
  async function refresh(){if(busy||document.hidden||list.contains(document.activeElement))return;busy=true;
    try{const response=await fetch(list.dataset.liveUrl,{credentials:'same-origin',cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();list.innerHTML=data.html;document.querySelector('[data-proposal-total]').textContent=data.total;const next=document.querySelector('[data-next-page]');if(next)next.hidden=data.total<=Number(list.dataset.page)*25;if(window.LANG)window.LANG.apply();document.querySelector('[data-live-state]').textContent='';}
    catch(error){const lang=window.LANG;document.querySelector('[data-live-state]').textContent=lang?lang.texts[lang.current]['voting.refresh_error']:'Automatic refresh unavailable; reload the page.';}
    finally{busy=false;}}
  setInterval(refresh,30000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
})();
