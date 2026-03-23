// AGH (AdGuard Home) page — SSH-proxied via control plane

var _aghNodeId = null;
var _aghConfig  = null;   // { agh_enabled, agh_host, agh_port, agh_web_user }

// ── Node selection ────────────────────────────────────────────────────────────

window.aghOnPageShow = function aghOnPageShow() {
  _aghBuildNodeSelect();
};

function _aghBuildNodeSelect() {
  var sel = document.getElementById('aghNodeSelect');
  if (!sel) return;
  var nodes = (window.NODES || []).filter(function(n) { return n.agh_enabled; });
  if (!nodes.length) {
    sel.innerHTML = '<option value="">No AGH nodes</option>';
    _aghNodeId = null;
    _aghRenderEmpty('No nodes have AGH enabled. Enable AGH in a node\'s config first.');
    return;
  }
  var prev = _aghNodeId;
  sel.innerHTML = nodes.map(function(n) {
    return '<option value="' + esc(n.id) + '"' + (n.id === prev ? ' selected' : '') + '>' + esc(n.name) + '</option>';
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
    var [configRes, statsRes, filterRes] = await Promise.allSettled([
      apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/config'),
      apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/stats'),
      apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/filtering'),
    ]);
    _aghConfig = configRes.status === 'fulfilled' ? configRes.value : null;
    var stats   = statsRes.status === 'fulfilled'  ? statsRes.value  : null;
    var filter  = filterRes.status === 'fulfilled' ? filterRes.value : null;
    _aghRender(_aghConfig, stats, filter, {
      statsErr:  statsRes.status  === 'rejected' ? statsRes.reason  : null,
      filterErr: filterRes.status === 'rejected' ? filterRes.reason : null,
    });
  } catch (err) {
    if (content) { content.innerHTML = '<div style="color:var(--red);padding:16px;">Load failed: ' + esc(String(err && err.message ? err.message : err)) + '</div>'; }
  }
};

// ── Rendering ─────────────────────────────────────────────────────────────────

function _aghRenderEmpty(msg) {
  var content = document.getElementById('aghContent');
  if (content) { content.innerHTML = '<div style="color:var(--t2);font-size:14px;padding:24px 0;">' + esc(msg) + '</div>'; }
}

function _aghRender(config, stats, filter, errs) {
  var content = document.getElementById('aghContent');
  if (!content) return;

  var html = '';

  // Config card
  html += '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Configuration</div>';
  html += rows([
    ['Host', (config ? (config.agh_host || '127.0.0.1') : '-') + ':' + (config ? (config.agh_port || 3000) : '-')],
    ['Web user', config ? (config.agh_web_user || '—') : '-'],
  ]);
  html += '<div class="dp-actions" style="margin-top:8px;">';
  html += '<button class="btn" onclick="aghOpenConfigModal()">EDIT CONFIG</button>';
  html += '</div></div>';

  // Stats card
  html += '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Statistics</div>';
  if (errs && errs.statsErr) {
    html += '<div style="color:var(--red);font-size:13px;">' + esc(String(errs.statsErr && errs.statsErr.message ? errs.statsErr.message : errs.statsErr)) + '</div>';
  } else if (stats) {
    html += rows([
      ['DNS queries (24h)',    String(stats.num_dns_queries          || 0)],
      ['Blocked today',        String(stats.num_blocked_filtering    || 0)],
      ['Replaced (safe)',      String(stats.num_replaced_safebrowsing|| 0)],
      ['Replaced (parental)',  String(stats.num_replaced_parental    || 0)],
      ['Avg processing time',  stats.avg_processing_time != null ? stats.avg_processing_time.toFixed(3) + ' ms' : '-'],
    ]);
    // Top domains table
    if (Array.isArray(stats.top_queried_domains) && stats.top_queried_domains.length) {
      html += '<div class="stitle" style="margin-top:12px;">Top Queried Domains</div>';
      html += '<div class="tw" style="margin-top:4px;"><table><thead><tr><th>Domain</th><th>Count</th></tr></thead><tbody>';
      html += stats.top_queried_domains.slice(0, 10).map(function(entry) {
        var domain = Object.keys(entry)[0];
        var count  = entry[domain];
        return '<tr><td>' + esc(domain) + '</td><td>' + esc(String(count)) + '</td></tr>';
      }).join('');
      html += '</tbody></table></div>';
    }
    // Top blocked
    if (Array.isArray(stats.top_blocked_domains) && stats.top_blocked_domains.length) {
      html += '<div class="stitle" style="margin-top:12px;">Top Blocked Domains</div>';
      html += '<div class="tw" style="margin-top:4px;"><table><thead><tr><th>Domain</th><th>Count</th></tr></thead><tbody>';
      html += stats.top_blocked_domains.slice(0, 10).map(function(entry) {
        var domain = Object.keys(entry)[0];
        var count  = entry[domain];
        return '<tr><td>' + esc(domain) + '</td><td>' + esc(String(count)) + '</td></tr>';
      }).join('');
      html += '</tbody></table></div>';
    }
  } else {
    html += '<div style="color:var(--t2);font-size:13px;">No stats available.</div>';
  }
  html += '</div>';

  // Filtering card
  html += '<div class="card" style="margin-bottom:16px;">';
  html += '<div class="stitle">Filtering Lists</div>';
  if (errs && errs.filterErr) {
    html += '<div style="color:var(--red);font-size:13px;">' + esc(String(errs.filterErr && errs.filterErr.message ? errs.filterErr.message : errs.filterErr)) + '</div>';
  } else if (filter) {
    html += rows([
      ['Protection enabled', filter.enabled ? 'yes' : 'no'],
      ['Active lists',       String((filter.filters || []).filter(function(f){ return f.enabled; }).length)],
      ['Total rules',        String((filter.filters || []).reduce(function(s, f){ return s + (f.rules_count || 0); }, 0))],
    ]);
    if (Array.isArray(filter.filters) && filter.filters.length) {
      html += '<div class="tw" style="margin-top:8px;"><table><thead><tr><th>Name</th><th>Rules</th><th>State</th><th>Actions</th></tr></thead><tbody>';
      html += filter.filters.map(function(f, idx) {
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

  content.innerHTML = html;
}

// ── AGH config modal ──────────────────────────────────────────────────────────

window.aghOpenConfigModal = function aghOpenConfigModal() {
  if (!_aghNodeId) return;
  var cfg = _aghConfig || {};
  var body = '<form id="aghConfigForm"><div class="modal-grid">'
    + formInput('AGH host', 'agh_host', cfg.agh_host || '127.0.0.1', {help: 'IP/hostname where AGH listens (on the node)'})
    + formInput('AGH port', 'agh_port', String(cfg.agh_port || 3000), {type: 'number'})
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
    agh_enabled: !!fd.agh_enabled,
    agh_host: fd.agh_host || '127.0.0.1',
    agh_port: parseInt(fd.agh_port, 10) || 3000,
    agh_web_user: fd.agh_web_user || null,
  };
  if (fd.agh_web_password) { payload.agh_web_password = fd.agh_web_password; }
  try {
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(_aghNodeId) + '/agh/config', {
      method: 'PUT',
      body: payload,
    });
    closeModal();
    // Refresh NODES list so selector reflects new agh_enabled state
    await window.refreshNodes?.();
    _aghBuildNodeSelect();
  } catch (err) {
    alert(err && err.message ? err.message : String(err));
  }
}

// ── Add filter list modal ─────────────────────────────────────────────────────

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
      body: { name: fd.name, url: fd.url, whitelist: !!fd.whitelist },
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
  var rules = (fd.rules || '').split('\n').map(function(r) { return r.trim(); }).filter(Boolean);
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

export {};
