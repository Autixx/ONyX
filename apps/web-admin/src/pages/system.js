// Page module - all functions exposed as window globals

// ── Chart data ──────────────────────────────────────────────────────────────
var _chartData = { cpu: [], ram: [], peers: [], net: [] };
var _chartMaxPts = 480;
var _chartWinMin = [5, 15, 30, 60];
var _chartWin = { cpu: 1, ram: 1, peers: 1, net: 1 };
var _chartRafPending = {};

function _pushChart(key, v) {
  var buf = _chartData[key];
  buf.push({ ts: Date.now(), v: v });
  if (buf.length > _chartMaxPts) buf.shift();
}

function _hexToRgb(hex) {
  hex = (hex || '#00c8b4').trim().replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(function(c){ return c+c; }).join('');
  var n = parseInt(hex, 16);
  return [(n>>16)&255, (n>>8)&255, n&255];
}

function _drawChart(canvasId, key, label, unit, yMax) {
  var canvas = document.getElementById(canvasId);
  if (!canvas) return;
  var wrap = canvas.parentElement;
  var W = wrap.clientWidth;
  var H = wrap.clientHeight;
  if (!W || !H) return;
  canvas.width = W;
  canvas.height = H;
  var ctx = canvas.getContext('2d');

  var winMs = _chartWinMin[_chartWin[key]] * 60000;
  var now = Date.now();
  var cutoff = now - winMs;
  var pts = _chartData[key].filter(function(p){ return p.ts >= cutoff; });

  var acc = getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() || '#00c8b4';
  var rgb = _hexToRgb(acc);
  var r = rgb[0], g = rgb[1], b = rgb[2];

  ctx.clearRect(0, 0, W, H);

  var pad = { l: 42, r: 10, t: 26, b: 20 };
  var cW = W - pad.l - pad.r;
  var cH = H - pad.t - pad.b;

  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.04)';
  ctx.lineWidth = 1;
  for (var i = 1; i <= 4; i++) {
    var gy = pad.t + cH * i / 4;
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(pad.l + cW, gy); ctx.stroke();
  }
  // Y-axis line
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + cH); ctx.stroke();

  // Label (top-left)
  ctx.fillStyle = 'rgba(255,255,255,0.45)';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'left';
  ctx.fillText(label, pad.l + 4, pad.t - 8);

  // Time window label (top-right)
  ctx.fillStyle = 'rgba(255,255,255,0.25)';
  ctx.font = '10px monospace';
  ctx.textAlign = 'right';
  ctx.fillText(_chartWinMin[_chartWin[key]] + ' min  (scroll to change)', W - 6, pad.t - 8);

  if (pts.length < 2) {
    ctx.fillStyle = 'rgba(255,255,255,0.18)';
    ctx.font = '12px monospace';
    ctx.textAlign = 'center';
    ctx.fillText('collecting data...', W / 2, pad.t + cH / 2);
    return;
  }

  var maxV = yMax != null ? yMax : Math.max.apply(null, pts.map(function(p){ return p.v; }));
  if (!maxV || maxV < 0.01) maxV = 1;

  function xOf(ts) { return pad.l + (ts - cutoff) / winMs * cW; }
  function yOf(v)  { return pad.t + cH - Math.min(1, v / maxV) * cH; }

  // Y-axis labels
  ctx.fillStyle = 'rgba(255,255,255,0.28)';
  ctx.font = '9px monospace';
  ctx.textAlign = 'right';
  [0, 0.25, 0.5, 0.75, 1].forEach(function(f) {
    var lv = maxV * f;
    var ly = pad.t + cH * (1 - f);
    var lbl = lv >= 10000 ? (lv/1000).toFixed(0)+'k' : lv >= 1000 ? (lv/1000).toFixed(1)+'k' : lv >= 10 ? lv.toFixed(0) : lv.toFixed(1);
    ctx.fillText(lbl + unit, pad.l - 3, ly + 3);
  });

  // X-axis time labels
  ctx.fillStyle = 'rgba(255,255,255,0.2)';
  ctx.font = '9px monospace';
  ctx.textAlign = 'center';
  var nTicks = 4;
  for (var ti = 0; ti <= nTicks; ti++) {
    var tts = cutoff + winMs * ti / nTicks;
    var d = new Date(tts);
    var tlbl = d.getHours().toString().padStart(2,'0') + ':' + d.getMinutes().toString().padStart(2,'0');
    ctx.fillText(tlbl, pad.l + cW * ti / nTicks, pad.t + cH + 14);
  }

  // Build path
  ctx.beginPath();
  pts.forEach(function(p, i) {
    var x = xOf(p.ts), y = yOf(p.v);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });

  // Stroke
  ctx.strokeStyle = 'rgba('+r+','+g+','+b+',0.9)';
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.stroke();

  // Fill
  var lastX = xOf(pts[pts.length-1].ts);
  var firstX = xOf(pts[0].ts);
  ctx.lineTo(lastX, pad.t + cH);
  ctx.lineTo(firstX, pad.t + cH);
  ctx.closePath();
  var grad = ctx.createLinearGradient(0, pad.t, 0, pad.t + cH);
  grad.addColorStop(0, 'rgba('+r+','+g+','+b+',0.28)');
  grad.addColorStop(1, 'rgba('+r+','+g+','+b+',0.02)');
  ctx.fillStyle = grad;
  ctx.fill();

  // Current value (top-right inside)
  var cur = pts[pts.length-1].v;
  var curStr = cur >= 10000 ? (cur/1000).toFixed(1)+'k' : cur >= 100 ? cur.toFixed(0) : cur.toFixed(1);
  ctx.fillStyle = 'rgba('+r+','+g+','+b+',0.95)';
  ctx.font = 'bold 16px monospace';
  ctx.textAlign = 'right';
  ctx.fillText(curStr + unit, W - 8, pad.t + 14);
}

function _requestChartRedraw(key, canvasId, label, unit, yMax) {
  if (_chartRafPending[key]) return;
  _chartRafPending[key] = true;
  requestAnimationFrame(function() {
    _chartRafPending[key] = false;
    _drawChart(canvasId, key, label, unit, yMax);
  });
}

function _redrawAllCharts() {
  _requestChartRedraw('cpu',   'chartCpu',   'CPU Load',       '%',    100);
  _requestChartRedraw('ram',   'chartRam',   'RAM Usage',      '%',    100);
  _requestChartRedraw('peers', 'chartPeers', 'Active Peers',   '',     null);
  _requestChartRedraw('net',   'chartNet',   'Network I/O',    ' KB/s',null);
}

function _attachChartScrollers() {
  var charts = ['cpu','ram','peers','net'];
  var canvasIds = {cpu:'chartCpu', ram:'chartRam', peers:'chartPeers', net:'chartNet'};
  var units = {cpu:'%', ram:'%', peers:'', net:' KB/s'};
  var yMaxes = {cpu:100, ram:100, peers:null, net:null};
  var labels = {cpu:'CPU Load', ram:'RAM Usage', peers:'Active Peers', net:'Network I/O'};
  charts.forEach(function(key) {
    var canvas = document.getElementById(canvasIds[key]);
    if (!canvas) return;
    canvas.addEventListener('wheel', function(e) {
      e.preventDefault();
      var dir = e.deltaY > 0 ? 1 : -1;
      _chartWin[key] = Math.max(0, Math.min(_chartWinMin.length - 1, _chartWin[key] + dir));
      _drawChart(canvasIds[key], key, labels[key], units[key], yMaxes[key]);
    }, { passive: false });
  });
}

// ── ResizeObserver for charts ───────────────────────────────────────────────
var _chartResizeObs = null;
function _initChartResize() {
  if (typeof ResizeObserver === 'undefined') return;
  if (_chartResizeObs) _chartResizeObs.disconnect();
  _chartResizeObs = new ResizeObserver(function() { _redrawAllCharts(); });
  ['chartCpu','chartRam','chartPeers','chartNet'].forEach(function(id){
    var el = document.getElementById(id);
    if (el && el.parentElement) _chartResizeObs.observe(el.parentElement);
  });
}

// ── Health & status ─────────────────────────────────────────────────────────
function statusLabel(status) {
  var s = String(status || 'unknown').toLowerCase();
  if (window.LANG === 'ru') {
    return ({ ok:'OK', degraded:'ДЕГРАДАЦИЯ', offline:'НЕ В СЕТИ', unknown:'НЕИЗВЕСТНО' })[s] || s.toUpperCase();
  }
  return s.toUpperCase();
}

function hpBarColor(pct) {
  var r, g;
  if (pct <= 50) { r = Math.round(pct/50*200); g = 180; }
  else { r = 200; g = Math.round((1-(pct-50)/50)*180); }
  return 'rgb('+r+','+g+',30)';
}

window.refreshHealth = async function refreshHealth() {
  var summary = await window.apiFetch(window.API_PREFIX + '/system/summary');
  var backend = (summary && summary.backend) || {};
  var worker  = (summary && summary.worker)  || {};
  var nodes   = (summary && summary.nodes)   || {};
  var links   = (summary && summary.links)   || {};
  var host    = (summary && summary.host)    || {};

  var backendOk = String(backend.status || summary.status || '').toLowerCase() === 'ok';
  var workerOk  = String(worker.status || '').toLowerCase() === 'ok';

  function _set(id, v) { var el=document.getElementById(id); if(el) el.textContent=v; }
  function _col(id, c) { var el=document.getElementById(id); if(el) el.style.color=c; }

  _set('sb', statusLabel(backend.status || summary.status));
  _col('sb', backendOk ? 'var(--grn)' : 'var(--amb)');

  _set('sw', statusLabel(worker.status));
  _col('sw', workerOk ? 'var(--grn)' : (String(worker.status||'').toLowerCase()==='offline' ? 'var(--red)' : 'var(--amb)'));

  _set('sn', String(nodes.online||0)+'/'+String(nodes.total||0));

  _set('sl', String(links.active||0));
  _col('sl', Number(links.degraded||0) > 0 ? 'var(--amb)' : 'var(--grn)');

  // Services total
  var svcsTotal = Number(summary.services_total || 0);
  _set('sServicesTotal', String(svcsTotal));
  _col('sServicesTotal', svcsTotal > 0 ? 'var(--acc)' : 'var(--t1)');

  // Support requests (from summary)
  var ticketsOpen = Number(summary.tickets_open || 0);
  _set('sOpenTickets', String(ticketsOpen));
  _col('sOpenTickets', ticketsOpen > 0 ? 'var(--amb)' : 'var(--grn)');

  // Topbar bars (still in topbar)
  var cpuPct = host.cpu_percent != null ? Math.round(Number(host.cpu_percent)) : null;
  var sysCpuEl = document.getElementById('sysCpu');
  var sysCpuFill = document.getElementById('sysCpuFill');
  if (cpuPct != null) {
    if (sysCpuEl) sysCpuEl.textContent = cpuPct + '%';
    if (sysCpuFill) { sysCpuFill.style.width = cpuPct+'%'; sysCpuFill.style.background = hpBarColor(cpuPct); }
    _pushChart('cpu', cpuPct);
  }

  if (host.memory_used_gb != null && host.memory_total_gb != null) {
    var ramUsed = Number(host.memory_used_gb);
    var ramTotal = Number(host.memory_total_gb);
    var ramPct = ramTotal > 0 ? Math.round(ramUsed / ramTotal * 100) : 0;
    var sysRamEl = document.getElementById('sysRam');
    var sysRamFill = document.getElementById('sysRamFill');
    if (sysRamEl) sysRamEl.textContent = ramUsed.toFixed(1)+'/'+ramTotal.toFixed(1)+' GB';
    if (sysRamFill) { sysRamFill.style.width = ramPct+'%'; sysRamFill.style.background = hpBarColor(ramPct); }
    _pushChart('ram', ramPct);
  }

  // Peer activity from summary
  var peersOnline = Number(summary.peers_online || 0);
  _pushChart('peers', peersOnline);

  // Network I/O
  var netKbps = Number((host.net_rx_kbps || 0)) + Number((host.net_tx_kbps || 0));
  _pushChart('net', Math.round(netKbps * 10) / 10);

  _redrawAllCharts();
  window.pushEv?.('system.ping', 'GET /api/v1/system/summary completed');
  window.scheduleLocaleRefresh?.();
};

window.healthCheck = async function healthCheck() {
  try { await window.refreshHealth(); }
  catch(err) { window.pushEv?.('system.error', String(err && err.message ? err.message : err)); }
};

window.startHealthPolling = function startHealthPolling() {
  if (window._healthPollTimer) clearInterval(window._healthPollTimer);
  window._healthPollTimer = setInterval(function() {
    window.refreshHealth().catch(function(err) {
      console.warn('health poll failed', err);
    });
  }, 15000);
};

// Legacy compat — no longer needed (data comes from summary) but keep stub
window.updateOpenTicketCount = function updateOpenTicketCount() {};

// Init charts on DOM ready
document.addEventListener('DOMContentLoaded', function() {
  _attachChartScrollers();
  _initChartResize();
  // Initial draw after a tick (so layout is settled)
  setTimeout(_redrawAllCharts, 100);
});

export {};
