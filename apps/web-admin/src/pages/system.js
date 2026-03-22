// Page module - all functions exposed as window globals

window.refreshHealth = async function refreshHealth(){
  var summary = await apiFetch(API_PREFIX + '/system/summary');
  var backend = (summary && summary.backend) || {};
  var worker = (summary && summary.worker) || {};
  var nodes = (summary && summary.nodes) || {};
  var links = (summary && summary.links) || {};
  var host = (summary && summary.host) || {};

  function statusLabel(status){
    var s = String(status || 'unknown').toLowerCase();
    if(LANG === 'ru'){
      return ({
        ok: 'OK',
        degraded: 'ДЕГРАДАЦИЯ',
        offline: 'НЕ В СЕТИ',
        unknown: 'НЕИЗВЕСТНО'
      })[s] || String(status || 'unknown').toUpperCase();
    }
    return String(status || 'unknown').toUpperCase();
  }

  var backendStatus = statusLabel(backend.status || summary.status || 'unknown');
  var workerStatus = statusLabel(worker.status || 'unknown');
  var backendOk = String(backend.status || summary.status || '').toLowerCase() === 'ok';
  var workerOk = String(worker.status || '').toLowerCase() === 'ok';

  var sb = document.getElementById('sb');
  var sw = document.getElementById('sw');
  var sn = document.getElementById('sn');
  var snSub = document.getElementById('snSub');
  var sl = document.getElementById('sl');
  var slSub = document.getElementById('slSub');

function hpBarColor(pct){
  var r,g;
  if(pct<=50){ r=Math.round(pct/50*200); g=180; }
  else { r=200; g=Math.round((1-(pct-50)/50)*180); }
  return 'rgb('+r+','+g+',30)';
}

  var sysCpu = document.getElementById('sysCpu');
  var sysRam = document.getElementById('sysRam');

  if(sb){
    sb.textContent = backendStatus;
    sb.style.color = backendOk ? 'var(--grn)' : 'var(--amb)';
  }
  if(sw){
    sw.textContent = workerStatus;
    sw.style.color = workerOk ? 'var(--grn)' : (String(worker.status || '').toLowerCase() === 'offline' ? 'var(--red)' : 'var(--amb)');
  }
  if(sn){
    sn.textContent = String(nodes.online || 0) + '/' + String(nodes.total || 0);
  }
  if(snSub){
    var degraded = Number(nodes.degraded || 0);
    var offline = Number(nodes.offline || 0);
    snSub.textContent = degraded > 0
      ? (LANG === 'ru' ? (degraded + ' в деградации') : (degraded + ' degraded'))
      : (offline > 0
        ? (LANG === 'ru' ? (offline + ' не в сети') : (offline + ' offline'))
        : (LANG === 'ru' ? 'все доступны' : 'all reachable'));
    snSub.style.color = degraded > 0 ? 'var(--amb)' : (offline > 0 ? 'var(--red)' : 'var(--grn)');
  }
  if(sl){
    sl.textContent = String(links.active || 0);
  }
  if(slSub){
    var degradedLinks = Number(links.degraded || 0);
    var totalLinks = Number(links.total || 0);
    var activeLinks = Number(links.active || 0);
    slSub.textContent = degradedLinks > 0
      ? (LANG === 'ru' ? (degradedLinks + ' в деградации') : (degradedLinks + ' degraded'))
      : ((activeLinks === totalLinks && totalLinks > 0)
        ? (LANG === 'ru' ? 'все активны' : 'all active')
        : (LANG === 'ru' ? (totalLinks + ' всего') : (totalLinks + ' total')));
    slSub.style.color = degradedLinks > 0 ? 'var(--amb)' : 'var(--grn)';
  }
  if(sysCpu && host.cpu_percent != null){
    var cpuPct = Math.round(Number(host.cpu_percent));
    sysCpu.textContent = cpuPct + '%';
    var cpuFill = document.getElementById('sysCpuFill');
    if(cpuFill){ cpuFill.style.width=cpuPct+'%'; cpuFill.style.background=hpBarColor(cpuPct); }
  }
  if(sysRam && host.memory_used_gb != null && host.memory_total_gb != null){
    var ramUsed = Number(host.memory_used_gb);
    var ramTotal = Number(host.memory_total_gb);
    var ramPct = ramTotal > 0 ? Math.round(ramUsed/ramTotal*100) : 0;
    sysRam.textContent = ramUsed.toFixed(1)+'/'+ramTotal.toFixed(1)+' GB';
    var ramFill = document.getElementById('sysRamFill');
    if(ramFill){ ramFill.style.width=ramPct+'%'; ramFill.style.background=hpBarColor(ramPct); }
  }
  pushEv('system.ping', 'GET /api/v1/system/summary completed');
  scheduleLocaleRefresh();
  updateOpenTicketCount();
};

window.updateOpenTicketCount = function updateOpenTicketCount() {
  apiFetch(API_PREFIX + '/admin/support-tickets?limit=500').then(function(data) {
    var count = 0;
    if (data && data.length) {
      count = data.filter(function(t){ return t.status === 'pending' || t.status === 'in_progress'; }).length;
    }
    var el = document.getElementById('sOpenTickets');
    if (!el) return;
    el.textContent = String(count);
    el.style.color = count > 0 ? 'var(--amb)' : 'var(--grn)';
    var card = document.getElementById('openTicketsCard');
    if (card) card.title = count > 0 ? (count + ' open ticket(s) — click to open Support Chat') : 'No open tickets';
  }).catch(function(){});
};

window.healthCheck = async function healthCheck(){
  try{ await refreshHealth(); }
  catch(err){ pushEv('system.error', String(err && err.message ? err.message : err)); }
};

window.startHealthPolling = function startHealthPolling(){
  if(_healthPollTimer) clearInterval(_healthPollTimer);
  _healthPollTimer = setInterval(function(){
    refreshHealth().catch(function(err){
      console.warn('health poll failed', err);
    });
  }, 15000);
};

export { refreshHealth, updateOpenTicketCount, healthCheck, startHealthPolling };
