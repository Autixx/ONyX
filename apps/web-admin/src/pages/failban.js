// Page module - all functions exposed as window globals

window._failbanTimer = null;
window._failbanPaused = false;

window.refreshFailban = async function refreshFailban(){
  if(window._failbanPaused) return;
  try{
    window.renderFailbanSourceTabs();
    var summary = await apiFetch(failbanSummaryPath());
    window.renderFailban(summary);
  }catch(err){
    window.renderFailban({
      installed: false,
      active: false,
      enabled: null,
      jails: [],
      recent_logs: [],
      timestamp: new Date().toISOString(),
      scope_kind: _failbanScopeKind,
      scope_node_id: _failbanScopeNodeId,
      scope_name: _failbanScopeKind === 'node' && currentFailbanNode() ? currentFailbanNode().name : 'control-plane',
      message: err && err.message ? err.message : String(err || 'Failed to load fail2ban status.'),
    });
  }
};

window.renderFailban = function renderFailban(summary){
  var el = document.getElementById('failban-log');
  if(!el) return;
  var lines = [];
  window.renderFailbanSourceTabs();
  var labelStatus = LANG === 'ru' ? 'статус' : 'status';
  var labelJails = LANG === 'ru' ? 'jails' : 'jails';
  var textLoadFailed = LANG === 'ru' ? 'Не удалось загрузить статус fail2ban.' : 'Failed to load fail2ban status.';
  var textNoLogs = LANG === 'ru' ? 'Нет свежих записей fail2ban.' : 'No recent fail2ban log entries.';
  var textActive = LANG === 'ru' ? 'active' : 'active';
  var textInactive = LANG === 'ru' ? 'inactive' : 'inactive';
  var textEnabled = LANG === 'ru' ? 'enabled' : 'enabled';
  var textDisabled = LANG === 'ru' ? 'disabled' : 'disabled';
  var textNotInstalled = LANG === 'ru' ? 'not installed' : 'not installed';
  if(!summary){
    lines.push('<div class="fline warning"><span class="ftime">--</span><span>'+esc(textLoadFailed)+'</span></div>');
    el.innerHTML = lines.join('');
    return;
  }
  var statusText = summary.installed
    ? ((summary.active ? textActive : textInactive) + (summary.enabled === true ? ', ' + textEnabled : summary.enabled === false ? ', ' + textDisabled : ''))
    : textNotInstalled;
  var jailNames = (summary.jails || []).map(function(j){ return j.name; }).join(', ') || '-';
  var sourceLabel = summary.scope_name || (_failbanScopeKind === 'node' && currentFailbanNode() ? currentFailbanNode().name : 'control-plane');
  lines.push('<div class="fline info"><span class="ftime">'+esc(fmtDateTime(summary.timestamp))+'</span><span>'+esc(sourceLabel)+' · '+esc(labelStatus)+': '+esc(statusText)+'; '+esc(labelJails)+': '+esc(jailNames)+'</span></div>');
  if(summary.message){
    lines.push('<div class="fline warning"><span class="ftime">'+esc(fmtDateTime(summary.timestamp))+'</span><span>'+esc(summary.message)+'</span></div>');
  }
  if((summary.recent_logs || []).length){
    lines = lines.concat(summary.recent_logs.map(function(entry){
      var source = entry.source ? ('[' + entry.source + '] ') : '';
      return '<div class="fline '+failbanEntryClass(entry)+'"><span class="ftime">'+esc(entry.created_at ? fmtDateTime(entry.created_at) : '--')+'</span><span>'+esc(source + entry.message)+'</span></div>';
    }));
  }else{
    lines.push('<div class="fline info"><span class="ftime">--</span><span>'+esc(textNoLogs)+'</span></div>');
  }
  el.innerHTML = lines.join('');
  el.scrollTop = el.scrollHeight;
};

window.renderFailbanSourceTabs = function renderFailbanSourceTabs(){
  var el = document.getElementById('failban-sources');
  var line = document.getElementById('failban-scope-line');
  if(!el || !line) return;
  if(_failbanScopeKind === 'node' && !currentFailbanNode()){
    _failbanScopeKind = 'control_plane';
    _failbanScopeNodeId = null;
  }
  var items = [{ kind:'control_plane', nodeId:null, label:(LANG === 'ru' ? 'Панель' : 'Control Plane') }]
    .concat((NODES || []).map(function(node){
      return { kind:'node', nodeId:node.id, label:node.name };
    }));
  el.innerHTML = items.map(function(item){
    var active = _failbanScopeKind === item.kind && String(_failbanScopeNodeId || '') === String(item.nodeId || '');
    return '<button class="failban-scope-tab '+(active ? 'active' : '')+'" onclick="selectFailbanScope(\''+esc(item.kind)+'\', '+(item.nodeId ? ('\''+esc(item.nodeId)+'\'') : 'null')+')">'+esc(item.label)+'</button>';
  }).join('');
  if(_failbanScopeKind === 'node' && currentFailbanNode()){
    line.textContent = (LANG === 'ru' ? 'Узел: ' : 'Node: ') + currentFailbanNode().name;
  }else{
    line.textContent = LANG === 'ru' ? 'Панель управления' : 'Control Plane';
  }
};

window.startFailbanPolling = function startFailbanPolling(){
  if(window._failbanTimer) clearInterval(window._failbanTimer);
  window._failbanTimer = setInterval(function(){ window.refreshFailban().catch(function(){}); }, 10000);
};

window.failbanPauseToggle = function failbanPauseToggle(){
  window._failbanPaused = !window._failbanPaused;
  document.getElementById('failbanPauseLabel').textContent = window._failbanPaused ? 'RESUME' : 'PAUSE';
};

export {};
