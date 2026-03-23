// AGH (AdGuard Home) page — SSH-proxied via control plane

var _aghNodeId = null;
var _aghConfig  = null;
var _aghTab = 'config';

// ── Node selection ────────────────────────────────────────────────────────────

window.aghOnPageShow = function aghOnPageShow() {
  _aghBuildNodeSelect();
};

function _aghDetectedDetails(nodeId) {
  return window.nodeDetectedAghDetails ? window.nodeDetectedAghDetails(nodeId) : null;
}

function _aghDetectedEndpoint(host, port) {
  var hostText = String(host || '').trim();
  var portNumber = parseInt(port, 10);
  if (!hostText) { return '-'; }
  return (portNumber > 0) ? (hostText + ':' + portNumber) : hostText;
}

function _aghBuildNodeSelect() {
  var sel = document.getElementById('aghNodeSelect');
  if (!sel) return;
  var nodes = (window.NODES || []).filter(function(n) {
    return n.agh_enabled || !!_aghDetectedDetails(n.id);
  });
  if (!nodes.length) {
    sel.innerHTML = '<option value="">No AGH nodes</option>';
    _aghNodeId = null;
    _aghRenderEmpty('No AGH nodes found. Install AGH and run Probe SSH, or enable AGH integration in a node config.');
    return;
  }
  var prev = _aghNodeId;
  sel.innerHTML = nodes.map(function(n) {
    var suffix = n.agh_enabled ? ' [configured]' : ' [detected]';
    return '<option value="' + esc(n.id) + '"' + (n.id === prev ? ' selected' : '') + '>' + esc(n.name + suffix) + '</option>';
  }).join('');
  var chosen = nodes.find(function(n) { return n.id === prev; }) || nodes[0];
  _aghNodeId = chosen.id;
  sel.value = _aghNodeId;
  aghRefresh();
}

window.aghSelectNode = function aghSelectNode(nodeId) {
  _aghNodeId = nodeId || null;
  if (_aghNodeId) { aghRefresh(); }
};

window.aghRefresh = async function aghRefresh() {
  if (!_aghNodeId) return;
  var content = document.getElementById('aghContent');
  if (content) { content.innerHTML = '<div style="color:var(--t2);padding:16px;">Loading…</div>'; }
  try {
    _aghConfig = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/config');
    var detected = _aghDetectedDetails(_aghNodeId);
    var stats = null;
    var filter = null;
    var errs = {};
    if (_aghConfig && _aghConfig.agh_enabled) {
      var [statsRes, filterRes] = await Promise.allSettled([
        apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/stats'),
        apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering'),
      ]);
      stats = statsRes.status === 'fulfilled' ? statsRes.value : null;
      filter = filterRes.status === 'fulfilled' ? filterRes.value : null;
      errs.statsErr = statsRes.status === 'rejected' ? statsRes.reason : null;
      errs.filterErr = filterRes.status === 'rejected' ? filterRes.reason : null;
    }
    _aghRender(_aghConfig, stats, filter, errs, detected);
  } catch (err) {
    if (content) { content.innerHTML = '<div style="color:var(--red);padding:16px;">Load failed: ' + esc(String(err && err.message ? err.message : err)) + '</div>'; }
  }
};

// ── Tab navigation ────────────────────────────────────────────────────────────

window.aghSwitchTab = function aghSwitchTab(tab) {
  _aghTab = tab;
  ['config', 'rules', 'querylog', 'peruser'].forEach(function(t) {
    var btn  = document.getElementById('aghTabBtn_' + t);
    var pane = document.getElementById('aghPane_' + t);
    if (btn)  { btn.classList.toggle('active', t === tab); }
    if (pane) { pane.style.display = t === tab ? '' : 'none'; }
  });
};

// ── Rendering entry ───────────────────────────────────────────────────────────

function _aghRenderEmpty(msg) {
  var content = document.getElementById('aghContent');
  if (content) { content.innerHTML = '<div style="color:var(--t2);font-size:14px;padding:24px 0;">' + esc(msg) + '</div>'; }
}

function _aghRender(config, stats, filter, errs, detected) {
  var content = document.getElementById('aghContent');
  if (!content) return;

  var integrationEnabled = !!(config && config.agh_enabled);

  var TAB_DEFS = [
    { id: 'config',   label: 'Config & Stats' },
    { id: 'rules',    label: 'Rules' },
    { id: 'querylog', label: 'Query Log' },
    { id: 'peruser',  label: 'Per-user Stats' },
  ];

  // Tab nav
  var html = '<div class="failban-sources" style="margin-bottom:16px;">';
  TAB_DEFS.forEach(function(tab) {
    html += '<button id="aghTabBtn_' + tab.id + '" class="failban-scope-tab' + (_aghTab === tab.id ? ' active' : '') + '" onclick="aghSwitchTab(\'' + tab.id + '\')">' + esc(tab.label) + '</button>';
  });
  html += '</div>';

  // Pane: Config & Stats
  html += '<div id="aghPane_config"' + (_aghTab !== 'config' ? ' style="display:none"' : '') + '>';
  html += _aghConfigStatsPane(config, stats, errs, detected, integrationEnabled);
  html += '</div>';

  // Pane: Rules
  html += '<div id="aghPane_rules"' + (_aghTab !== 'rules' ? ' style="display:none"' : '') + '>';
  html += _aghRulesPane(filter, errs, integrationEnabled);
  html += '</div>';

  // Pane: Query Log
  html += '<div id="aghPane_querylog"' + (_aghTab !== 'querylog' ? ' style="display:none"' : '') + '>';
  if (integrationEnabled) {
    html += _aghQuerylogPane();
  } else {
    html += '<div style="color:var(--t2);font-size:13px;padding:16px 0;">Enable AGH integration to use query log.</div>';
  }
  html += '</div>';

  // Pane: Per-user Stats
  html += '<div id="aghPane_peruser"' + (_aghTab !== 'peruser' ? ' style="display:none"' : '') + '>';
  if (integrationEnabled) {
    html += _aghPerUserPane();
  } else {
    html += '<div style="color:var(--t2);font-size:13px;padding:16px 0;">Enable AGH integration to use per-user statistics.</div>';
  }
  html += '</div>';

  content.innerHTML = html;
}

// ── Pane: Config & Stats ──────────────────────────────────────────────────────

function _aghConfigStatsPane(config, stats, errs, detected, integrationEnabled) {
  var probeState = detected ? (detected.active ? 'active' : 'installed') : 'not detected';
  if (detected && detected.service_active_state && detected.service_active_state !== 'active') {
    probeState += ' (' + detected.service_active_state + ')';
  }
  var html = '';

  // Config card
  html += '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Configuration</div>';
  html += rows([
    ['Integration',    integrationEnabled ? 'enabled' : 'disabled'],
    ['Configured API', (config ? (config.agh_host || '127.0.0.1') : '-') + ':' + (config ? (config.agh_port || 3000) : '-')],
    ['Detected web',   detected ? _aghDetectedEndpoint(detected.http_host, detected.http_port) : '-'],
    ['Detected DNS',   detected ? _aghDetectedEndpoint(detected.dns_host, detected.dns_port || 53) : '-'],
    ['Probe status',   probeState],
    ['Web user',       config ? (config.agh_web_user || '—') : '-'],
  ]);
  if (!integrationEnabled) {
    html += '<div style="margin-top:10px;color:var(--t2);font-size:13px;">'
      + esc(detected
        ? 'AdGuard Home was detected by Probe SSH. Review the API endpoint, then enable AGH integration for this node to use dashboard actions.'
        : 'AGH integration is disabled for this node. Install AGH and run Probe SSH, or fill the config manually.')
      + '</div>';
  }
  html += '<div class="dp-actions" style="margin-top:8px;"><button class="btn" onclick="aghOpenConfigModal()">EDIT CONFIG</button></div>';
  html += '</div>';

  // Stats card
  html += '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Statistics</div>';
  if (errs && errs.statsErr) {
    html += '<div style="color:var(--red);font-size:13px;">' + esc(String(errs.statsErr && errs.statsErr.message ? errs.statsErr.message : errs.statsErr)) + '</div>';
  } else if (stats) {
    html += rows([
      ['DNS queries (24h)',   String(stats.num_dns_queries           || 0)],
      ['Blocked today',       String(stats.num_blocked_filtering     || 0)],
      ['Replaced (safe)',     String(stats.num_replaced_safebrowsing || 0)],
      ['Replaced (parental)', String(stats.num_replaced_parental     || 0)],
      ['Avg processing',      stats.avg_processing_time != null ? stats.avg_processing_time.toFixed(3) + ' ms' : '-'],
    ]);
    if (Array.isArray(stats.top_queried_domains) && stats.top_queried_domains.length) {
      html += '<div class="stitle" style="margin-top:12px;">Top Queried Domains</div>';
      html += '<div class="tw" style="margin-top:4px;"><table><thead><tr><th>Domain</th><th>Count</th></tr></thead><tbody>';
      html += stats.top_queried_domains.slice(0, 10).map(function(e) {
        var d = Object.keys(e)[0]; return '<tr><td>' + esc(d) + '</td><td>' + esc(String(e[d])) + '</td></tr>';
      }).join('');
      html += '</tbody></table></div>';
    }
    if (Array.isArray(stats.top_blocked_domains) && stats.top_blocked_domains.length) {
      html += '<div class="stitle" style="margin-top:12px;">Top Blocked Domains</div>';
      html += '<div class="tw" style="margin-top:4px;"><table><thead><tr><th>Domain</th><th>Count</th></tr></thead><tbody>';
      html += stats.top_blocked_domains.slice(0, 10).map(function(e) {
        var d = Object.keys(e)[0]; return '<tr><td>' + esc(d) + '</td><td>' + esc(String(e[d])) + '</td></tr>';
      }).join('');
      html += '</tbody></table></div>';
    }
  } else {
    html += '<div style="color:var(--t2);font-size:13px;">No stats available.</div>';
  }
  html += '</div>';

  return html;
}

// ── Pane: Rules ───────────────────────────────────────────────────────────────

function _aghRulesPane(filter, errs, integrationEnabled) {
  var html = '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Filtering Lists</div>';
  if (!integrationEnabled) {
    html += '<div style="color:var(--t2);font-size:13px;">Enable AGH integration to manage filter lists.</div>';
  } else if (errs && errs.filterErr) {
    html += '<div style="color:var(--red);font-size:13px;">' + esc(String(errs.filterErr && errs.filterErr.message ? errs.filterErr.message : errs.filterErr)) + '</div>';
  } else if (filter) {
    html += rows([
      ['Protection enabled', filter.enabled ? 'yes' : 'no'],
      ['Active lists',       String((filter.filters || []).filter(function(f){ return f.enabled; }).length)],
      ['Total rules',        String((filter.filters || []).reduce(function(s, f){ return s + (f.rules_count || 0); }, 0))],
    ]);
    if (Array.isArray(filter.filters) && filter.filters.length) {
      html += '<div class="tw" style="margin-top:8px;"><table><thead><tr><th>Name</th><th>Rules</th><th>State</th><th>Actions</th></tr></thead><tbody>';
      html += filter.filters.map(function(f) {
        return '<tr>'
          + '<td>' + esc(f.name || f.url || '—') + '</td>'
          + '<td>' + esc(String(f.rules_count || 0)) + '</td>'
          + '<td>' + (f.enabled ? '<span class="pill pg">on</span>' : '<span class="pill pq">off</span>') + '</td>'
          + '<td><button class="btn sm" onclick="aghRemoveFilterList(' + JSON.stringify(f.url) + ',' + JSON.stringify(!!f.whitelist) + ')">REMOVE</button></td>'
          + '</tr>';
      }).join('');
      html += '</tbody></table></div>';
    }
    html += '<div class="dp-actions" style="margin-top:8px;">';
    html += '<button class="btn" onclick="aghOpenAddListModal()">ADD LIST</button>';
    html += '<button class="btn" onclick="aghOpenCustomRulesModal(' + JSON.stringify((filter.user_rules || []).join('\n')) + ')">CUSTOM RULES</button>';
    html += '<button class="btn" onclick="aghRefreshLists()">REFRESH LISTS</button>';
    html += '</div>';
  } else {
    html += '<div style="color:var(--t2);font-size:13px;">No filter data available.</div>';
  }
  html += '</div>';
  return html;
}

// ── Pane: Query Log ───────────────────────────────────────────────────────────

function _aghQuerylogPane() {
  var html = '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Query Log</div>';
  html += '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">';
  html += '<input id="aghLogSearch" class="mf-input" placeholder="Domain search…" style="width:220px;padding:6px 10px;font-size:13px;" onkeydown="if(event.key===\'Enter\')aghLoadQuerylog()">';
  html += '<select id="aghLogStatus" class="mf-select" style="width:160px;padding:6px 10px;font-size:13px;">'
    + '<option value="">All responses</option>'
    + '<option value="filtered">Filtered/Blocked</option>'
    + '<option value="processed">Allowed</option>'
    + '</select>';
  html += '<button class="btn" onclick="aghLoadQuerylog()">SEARCH</button>';
  html += '</div>';
  html += '<div id="aghLogTable"><div style="color:var(--t2);font-size:13px;">Press SEARCH to load query log.</div></div>';
  html += '</div>';
  return html;
}

window.aghLoadQuerylog = async function aghLoadQuerylog() {
  if (!_aghNodeId) return;
  var searchEl  = document.getElementById('aghLogSearch');
  var statusSel = document.getElementById('aghLogStatus');
  var search    = searchEl  ? searchEl.value.trim()  : '';
  var status    = statusSel ? statusSel.value        : '';

  var tableEl = document.getElementById('aghLogTable');
  if (tableEl) { tableEl.innerHTML = '<div style="color:var(--t2);font-size:13px;">Loading…</div>'; }

  var qs = '?limit=200';
  if (search)  { qs += '&search='          + encodeURIComponent(search); }
  if (status)  { qs += '&response_status=' + encodeURIComponent(status); }

  try {
    var data = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/querylog' + qs);
    tableEl.innerHTML = _aghRenderLogTable(data);
  } catch (err) {
    if (tableEl) { tableEl.innerHTML = '<div style="color:var(--red);font-size:13px;">' + esc(String(err && err.message ? err.message : err)) + '</div>'; }
  }
};

// ── Pane: Per-user Stats ──────────────────────────────────────────────────────

function _aghPerUserPane() {
  var peers = (window.PEERS || []).filter(function(p) { return p.is_active !== false && !p.revoked_at; });
  var peerOpts = '<option value="">— select user —</option>';
  peers.forEach(function(p) {
    var ip = p.awg_address_v4 || p.wg_address_v4 || '';
    var label = p.username || p.email || p.id;
    if (ip) { label += ' (' + ip + ')'; }
    peerOpts += '<option value="' + esc(ip || p.id) + '">' + esc(label) + '</option>';
  });

  var html = '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Per-user Statistics</div>';
  html += '<div style="color:var(--t2);font-size:12px;margin-bottom:8px;">Select a known user from the list, or type an IP address manually.</div>';
  html += '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">';
  html += '<select id="aghPerUserSel" class="mf-select" style="width:240px;padding:6px 10px;font-size:13px;" onchange="document.getElementById(\'aghPerUserIP\').value=this.value">' + peerOpts + '</select>';
  html += '<input id="aghPerUserIP" class="mf-input" placeholder="IP or username…" style="width:180px;padding:6px 10px;font-size:13px;" onkeydown="if(event.key===\'Enter\')aghLoadPerUserLog()">';
  html += '<input id="aghPerUserDomain" class="mf-input" placeholder="Domain filter…" style="width:180px;padding:6px 10px;font-size:13px;" onkeydown="if(event.key===\'Enter\')aghLoadPerUserLog()">';
  html += '<button class="btn" onclick="aghLoadPerUserLog()">SEARCH</button>';
  html += '</div>';
  html += '<div id="aghPerUserTable"><div style="color:var(--t2);font-size:13px;">Select a user and press SEARCH.</div></div>';
  html += '</div>';
  return html;
}

window.aghLoadPerUserLog = async function aghLoadPerUserLog() {
  if (!_aghNodeId) return;
  var ipEl     = document.getElementById('aghPerUserIP');
  var domainEl = document.getElementById('aghPerUserDomain');
  var raw      = ipEl ? ipEl.value.trim() : '';
  var domain   = domainEl ? domainEl.value.trim() : '';

  if (!raw) { alert('Enter a username or IP address.'); return; }

  // Resolve username → IP via PEERS
  var client = raw;
  var peers = window.PEERS || [];
  var peer = peers.find(function(p) {
    return (p.username || '').toLowerCase() === raw.toLowerCase()
        || (p.email    || '').toLowerCase() === raw.toLowerCase();
  });
  if (peer) {
    client = peer.awg_address_v4 || peer.wg_address_v4 || raw;
  }

  var tableEl = document.getElementById('aghPerUserTable');
  if (tableEl) { tableEl.innerHTML = '<div style="color:var(--t2);font-size:13px;">Loading…</div>'; }

  var qs = '?limit=500&client=' + encodeURIComponent(client);
  if (domain) { qs += '&search=' + encodeURIComponent(domain); }

  try {
    var data = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/querylog' + qs);
    tableEl.innerHTML = _aghRenderLogTable(data);
  } catch (err) {
    if (tableEl) { tableEl.innerHTML = '<div style="color:var(--red);font-size:13px;">' + esc(String(err && err.message ? err.message : err)) + '</div>'; }
  }
};

// ── Shared: render query log table ────────────────────────────────────────────

function _aghRenderLogTable(data) {
  var entries = Array.isArray(data) ? data : (data && Array.isArray(data.data) ? data.data : []);
  if (!entries.length) {
    return '<div style="color:var(--t2);font-size:13px;">No entries found.</div>';
  }
  var html = '<div class="tw"><table><thead><tr>'
    + '<th>Time</th><th>Client</th><th>Domain</th><th>Type</th><th>Status</th><th>Duration</th>'
    + '</tr></thead><tbody>';
  html += entries.map(function(e) {
    var t         = e.time ? new Date(e.time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '-';
    var clientStr = esc(e.client || '-');
    var peerName  = _aghResolvePeer(e.client);
    if (peerName) { clientStr = esc(peerName) + ' <span style="color:var(--t2);font-size:11px;">(' + esc(e.client) + ')</span>'; }
    var domain    = esc(e.question && e.question.name ? e.question.name : '-');
    var qtype     = esc(e.question && e.question.type ? e.question.type : '-');
    var isBlocked = e.reason && (e.reason.indexOf('Filter') !== -1 || e.reason.indexOf('Block') !== -1 || e.reason === 'FilteredBlacklist');
    var statusPill = isBlocked
      ? '<span class="pill" style="background:var(--red);color:#fff;font-size:11px;">blocked</span>'
      : '<span class="pill pq" style="font-size:11px;">' + esc(e.reason || 'ok') + '</span>';
    var dur = e.elapsed_ms != null ? e.elapsed_ms.toFixed(1) + ' ms' : '-';
    return '<tr>'
      + '<td style="white-space:nowrap;font-size:12px;">' + t + '</td>'
      + '<td>' + clientStr + '</td>'
      + '<td style="word-break:break-all;">' + domain + '</td>'
      + '<td style="font-size:12px;">' + qtype + '</td>'
      + '<td>' + statusPill + '</td>'
      + '<td style="font-size:12px;">' + esc(dur) + '</td>'
      + '</tr>';
  }).join('');
  html += '</tbody></table></div>';
  return html;
}

function _aghResolvePeer(ip) {
  if (!ip) return null;
  var p = (window.PEERS || []).find(function(p) {
    return p.awg_address_v4 === ip || p.wg_address_v4 === ip;
  });
  return p ? (p.username || p.email || null) : null;
}

// ── AGH config modal ──────────────────────────────────────────────────────────

window.aghOpenConfigModal = function aghOpenConfigModal() {
  if (!_aghNodeId) return;
  var cfg = _aghConfig || {};
  var detected = _aghDetectedDetails(_aghNodeId) || {};
  var detectedHost = detected.http_host || '';
  if (detectedHost === '0.0.0.0' || detectedHost === '::' || detectedHost === '[::]') {
    detectedHost = '127.0.0.1';
  }
  var defaultHost = cfg.agh_host || detectedHost || '127.0.0.1';
  var defaultPort = cfg.agh_port || detected.http_port || 3000;
  var body = '<form id="aghConfigForm"><div class="modal-grid">'
    + formInput('AGH host', 'agh_host', defaultHost, {help: 'IP/hostname where AGH listens (on the node). Probe SSH values are used as defaults when available.'})
    + formInput('AGH port', 'agh_port', String(defaultPort), {type: 'number'})
    + formInput('Web username', 'agh_web_user', cfg.agh_web_user || '')
    + formInput('Web password', 'agh_web_password', '', {type: 'password', help: 'Leave blank to keep existing'})
    + formCheckbox('AGH enabled', 'agh_enabled', !!cfg.agh_enabled, {caption: 'Enable AGH integration for this node'})
    + '</div></form>';
  openModal('AGH Configuration', body, {
    buttons: [
      {label: 'Cancel', className: 'btn', onClick: closeModal},
      {label: 'Save', className: 'btn pri', onClick: function() { document.getElementById('aghConfigForm').requestSubmit(); }},
    ],
  });
  bindModalForm('aghConfigForm', function(fd) { _aghSaveConfig(fd); });
};

async function _aghSaveConfig(fd) {
  var payload = {
    agh_enabled: fd.get('agh_enabled') === 'on',
    agh_host: fd.get('agh_host') || '127.0.0.1',
    agh_port: parseInt(fd.get('agh_port'), 10) || 3000,
    agh_web_user: fd.get('agh_web_user') || null,
  };
  if (fd.get('agh_web_password')) { payload.agh_web_password = fd.get('agh_web_password'); }
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/config', {
      method: 'PUT',
      body: payload,
    });
    closeModal();
    await window.refreshNodes?.();
    _aghBuildNodeSelect();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
}

// ── Filter list modals ────────────────────────────────────────────────────────

window.aghOpenAddListModal = function aghOpenAddListModal() {
  var body = '<form id="aghAddListForm"><div class="modal-grid">'
    + formInput('Name', 'name', '', {required: true})
    + formInput('URL', 'url', '', {required: true, help: 'Blocklist URL'})
    + formCheckbox('Whitelist', 'whitelist', false, {caption: 'This is an allowlist (whitelist)'})
    + '</div></form>';
  openModal('Add Filter List', body, {
    buttons: [
      {label: 'Cancel', className: 'btn', onClick: closeModal},
      {label: 'Add', className: 'btn pri', onClick: function() { document.getElementById('aghAddListForm').requestSubmit(); }},
    ],
  });
  bindModalForm('aghAddListForm', function(fd) { _aghSubmitAddList(fd); });
};

async function _aghSubmitAddList(fd) {
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering/lists/add', {
      method: 'POST',
      body: { name: fd.get('name'), url: fd.get('url'), whitelist: fd.get('whitelist') === 'on' },
    });
    closeModal();
    aghRefresh();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
}

window.aghRemoveFilterList = async function aghRemoveFilterList(url, whitelist) {
  if (!confirm('Remove filter list: ' + url + '?')) return;
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering/lists/remove', {
      method: 'POST',
      body: { url: url, whitelist: whitelist },
    });
    aghRefresh();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
};

window.aghRefreshLists = async function aghRefreshLists() {
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering/refresh', { method: 'POST' });
    aghRefresh();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
};

// ── Custom rules modal ────────────────────────────────────────────────────────

window.aghOpenCustomRulesModal = function aghOpenCustomRulesModal(currentRules) {
  var body = '<form id="aghCustomRulesForm"><div class="modal-grid">'
    + formTextarea('Custom rules', 'rules', currentRules || '', {full: true, help: 'One rule per line. Standard AdGuard / uBlock syntax.'})
    + '</div></form>';
  openModal('Custom Filtering Rules', body, {
    buttons: [
      {label: 'Cancel', className: 'btn', onClick: closeModal},
      {label: 'Save', className: 'btn pri', onClick: function() { document.getElementById('aghCustomRulesForm').requestSubmit(); }},
    ],
  });
  bindModalForm('aghCustomRulesForm', function(fd) { _aghSaveCustomRules(fd); });
};

async function _aghSaveCustomRules(fd) {
  var rules = (fd.get('rules') || '').split('\n').map(function(r) { return r.trim(); }).filter(Boolean);
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering/rules', {
      method: 'POST',
      body: { rules: rules },
    });
    closeModal();
    aghRefresh();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
}

// ── Install AGH modal ─────────────────────────────────────────────────────────

window.aghOpenInstallModal = function aghOpenInstallModal() {
  var nodes = window.NODES || [];
  if (!nodes.length) { alert('No nodes available.'); return; }
  var nodeOpts = nodes.map(function(n) {
    return '<option value="' + esc(n.id) + '">' + esc(n.name) + '</option>';
  }).join('');
  var body = '<form id="aghInstallForm">'
    + '<div class="modal-grid">'
    + '<div class="mf-row"><label class="mf-label">Target node</label>'
    + '<select id="aghInstallNodeSel" name="node_id" class="mf-select" style="width:100%;">' + nodeOpts + '</select></div>'
    + '</div>'
    + '<div style="margin-top:14px;padding:10px 12px;background:var(--bg2);border-radius:6px;border:1px solid var(--bdr);font-size:13px;color:var(--t2);">'
    + '<strong style="color:var(--t1);">Warning:</strong> This will enqueue an <strong>install-agh</strong> job on the selected node. '
    + 'The job runs the official AdGuard Home installer script via SSH and may take several minutes. '
    + 'Progress is visible in <em>Network → Jobs</em>.'
    + '</div>'
    + '</form>';
  openModal('Install AdGuard Home on Node', body, {
    buttons: [
      {label: 'Cancel', className: 'btn', onClick: closeModal},
      {label: 'Install', className: 'btn pri', onClick: _aghSubmitInstall},
    ],
  });
};

async function _aghSubmitInstall() {
  var sel = document.getElementById('aghInstallNodeSel');
  var nodeId = sel ? sel.value : null;
  if (!nodeId) { alert('Select a node.'); return; }
  try {
    var job = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId) + '/install-agh', { method: 'POST' });
    closeModal();
    alert('Install AGH job enqueued: ' + (job && job.id ? job.id : '?') + '\nTrack progress in Network → Jobs.');
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
}

export {};
