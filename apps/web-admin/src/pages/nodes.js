// Page module - all functions exposed as window globals

window.nodeInterfaceList = function nodeInterfaceList(nodeId){
  var node = nById(nodeId);
  var raw = Array.isArray(node.discovered_interfaces) ? node.discovered_interfaces : [];
  var seen = {};
  return raw.map(function(item){ return String(item || '').trim(); }).filter(function(item){
    if(!item || seen[item]) return false;
    seen[item] = true;
    return true;
  });
};

window.renderNodes = function renderNodes(){
  var filters = getNodeFilters();
  var rowsData = NODES.filter(function(n){
    var haystack = [
      n.name,
      n.role,
      n.management_address,
      n.status,
      (n.caps || []).join(' ')
    ].join(' ').toLowerCase();
    if(filters.search && haystack.indexOf(filters.search) === -1){ return false; }
    if(filters.status && String(n.status || '').toLowerCase() !== filters.status){ return false; }
    return true;
  });
  document.getElementById('ntb').innerHTML = rowsData.length ? rowsData.map(function(n){
    var trafficPct = (n.traffic_limit_gb && n.traffic_used_gb != null) ? n.traffic_used_gb/n.traffic_limit_gb : null;
    var trafficCls = trafficPct >= 1.0 ? 'traffic-crit' : trafficPct >= 0.8 ? 'traffic-warn' : '';
    return '<tr onclick="showNode(\''+esc(n.id)+'\')">'
      +'<td class="m">'+esc(n.name)+'</td>'
      +'<td>'+rp(n.role)+'</td>'
      +'<td class="m">'+esc(n.management_address)+'</td>'
      +'<td>'+sp(n.status)+'</td>'
      +'<td class="'+trafficCls+'">'+(n.traffic_used_gb != null ? n.traffic_used_gb+' GB' : '-')+'</td>'+'<td style="color:var(--t1)">'+(n.traffic_limit_gb ? n.traffic_limit_gb+' GB' : '—')+'</td>'+'<td style="color:var(--t2);font-size:13px;">'+esc((n.caps||[]).join(', ') || '-')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionNodeDiscover(\''+esc(n.id)+'\')">PROBE</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionNodeBootstrap(\''+esc(n.id)+'\')">BOOTSTRAP</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();actionNodeForceReboot(\''+esc(n.id)+'\')">REBOOT</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openNodeModal(\''+esc(n.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteNodeFlow(\''+esc(n.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('') : '<tr><td class="empty-state" colspan="6">No nodes match the current filter.</td></tr>';
};

window.showNode = function showNode(id){
  var n = NODES.find(function(x){return x.id===id;}); if(!n) return;
  var baseHtml =
    rows([
      ['ID',n.id],
      ['Role',n.role],
      ['Mgmt Address',n.management_address],
      ['SSH Host',n.ssh_host],
      ['SSH Port',n.ssh_port],
      ['SSH User',n.ssh_user],
      ['Auth Type',n.auth_type],
      ['Status',n.status],
      ['Capabilities',(n.caps||[]).join(', ') || '-'],
      ['Traffic Used', n.traffic_used_gb != null ? String(n.traffic_used_gb) + ' GB' : '-'],
      ['Traffic Limit', n.traffic_limit_gb != null ? String(n.traffic_limit_gb) + ' GB' : '-'],
      ['Traffic Suspended', n.traffic_suspended_at ? 'yes' : 'no'],
      ['Suspension Reason', n.traffic_suspension_reason || '-'],
      ['Hard Enforced', n.traffic_hard_enforced_at ? 'yes' : 'no'],
      ['Hard Enforcement Reason', n.traffic_hard_enforcement_reason || '-']
    ])
    +'<div id="nodeSecurityBox" style="margin-top:14px;color:var(--t1);font-size:13px;">Loading node security status…</div>'
    +'<div id="nodeTrafficBox" style="margin-top:14px;color:var(--t1);font-size:13px;">Loading node traffic cycle…</div>'
    +'<div id="nodeTrafficEventsInlineBox" style="margin-top:14px;color:var(--t1);font-size:13px;">Loading traffic events…</div>'
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="actionNodeDiscover(\''+esc(n.id)+'\')">PROBE SSH</button>'
      +'<button class="btn pri" onclick="actionNodeBootstrap(\''+esc(n.id)+'\')">BOOTSTRAP</button>'
      +'<button class="btn" onclick="openNodeNetworkTestModal(\''+esc(n.id)+'\')">NETWORK TEST</button>'
      +'<button class="btn" onclick="loadNodeSecurityStatus(\''+esc(n.id)+'\')">REFRESH SECURITY</button>'
      +'<button class="btn red" onclick="actionNodeForceReboot(\''+esc(n.id)+'\')">FORCE REBOOT</button>'
      +'<button class="btn" onclick="openNodeModal(\''+esc(n.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteNodeFlow(\''+esc(n.id)+'\')">DELETE</button>'
    +'</div>';
  openDP(n.name, baseHtml, { kind:'node', id:n.id });
  loadNodeSecurityStatus(n.id);
  apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(n.id) + '/traffic')
    .then(function(overview){
      var box = document.getElementById('nodeTrafficBox');
      if(!box || !overview || !overview.current_cycle) return;
      var current = overview.current_cycle;
      var ratio = current.usage_ratio != null ? (Math.round(current.usage_ratio * 1000) / 10) + '%' : '-';
      var recent = (overview.recent_cycles || []).slice(0, 4).map(function(cycle){
        return '<div class="drow"><span class="dk">'+esc(fmtDate(cycle.cycle_started_at))+'</span><span class="dv">'+esc(String(cycle.used_gb)+' GB')+'</span></div>';
      }).join('');
      box.innerHTML =
        '<div class="dp-sep"></div>'
        + rows([
          ['Cycle Start', fmtDate(current.cycle_started_at)],
          ['Cycle End', fmtDate(current.cycle_ends_at)],
          ['Usage Ratio', ratio],
          ['Hard Enforced', overview.traffic_hard_enforced_at ? 'yes' : 'no'],
          ['Hard Enforcement Reason', overview.traffic_hard_enforcement_reason || '-'],
          ['Warning Triggered', current.warning_emitted_at ? fmtDate(current.warning_emitted_at) : '-'],
          ['Exceeded Triggered', current.exceeded_emitted_at ? fmtDate(current.exceeded_emitted_at) : '-']
        ])
        + '<div style="margin-top:10px;color:var(--t2);font-size:12px;text-transform:uppercase;letter-spacing:.12em;">Recent Cycles</div>'
        + '<div style="margin-top:8px;">' + (recent || '<div class="drow"><span class="dk">No data</span><span class="dv">-</span></div>') + '</div>';
      loadNodeTrafficEvents(n.id, 'nodeTrafficEventsInlineBox');
    })
    .catch(function(){
      var box = document.getElementById('nodeTrafficBox');
      if(box) box.innerHTML = '<div style="color:var(--rd)">Failed to load node traffic cycle.</div>';
    });
};

window.openNodeModal = function openNodeModal(nodeId){
  var node = nodeId ? nById(nodeId) : null;
  var authType = node ? node.auth_type : 'password';
  var body = '<form id="nodeForm"><div class="modal-grid">'
    +formInput('Name', 'name', node ? node.name : '', {required:true})
    +formSelect('Role', 'role', node ? node.role : 'mixed', ['gateway','relay','egress','mixed'])
    +formInput('Management address', 'management_address', node ? node.management_address : '', {required:true})
    +formInput('SSH host', 'ssh_host', node ? node.ssh_host : '', {required:true})
    +formInput('SSH port', 'ssh_port', node ? node.ssh_port : '22', {required:true, type:'number'})
    +formInput('SSH user', 'ssh_user', node ? node.ssh_user : 'root', {required:true})
    +formSelect('Auth type', 'auth_type', authType, ['password','private_key'])
    +formInput('Traffic threshold (GB)', 'traffic_limit_gb', node && node.traffic_limit_gb != null ? String(node.traffic_limit_gb) : '', {type:'number', step:'0.1', min:'0', help:'Optional monthly or cycle threshold in gigabytes.'})
    +formTextarea(node ? 'New secret (optional)' : 'Secret', 'secret_value', '', {help: node ? 'Leave empty to keep current secret.' : 'Password or private key depending on auth type.'})
    +'</div></form>';
  openModal(node ? 'Edit Node' : 'Create Node', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: node ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('nodeForm').requestSubmit(); }}
    ]
  });
  bindModalForm('nodeForm', function(fd){ saveNodeForm(fd, nodeId); });
};

window.deleteNodeFlow = async function deleteNodeFlow(nodeId){
  var node = nById(nodeId);
  if(!confirm('Delete node ' + (node.name || nodeId) + '?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId), { method:'DELETE' });
    pushEv('node.deleted', 'node ' + (node.name || nodeId) + ' deleted');
    closeDP();
    await refreshNodes();
  }catch(err){
    pushEv('node.delete.error', 'delete failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionNodeDiscover = async function actionNodeDiscover(nodeId){
  try{
    var node = nById(nodeId);
    var job = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId) + '/discover', { method:'POST', body:{} });
    pushEv('job.created', 'discover queued for ' + (node.name || nodeId) + ' [' + job.id + ']');
    showToast('Probe SSH queued: ' + (node.name || nodeId) + ' [' + job.id + ']', 'success', 'Job queued');
    await refreshJobs();
    setTimeout(function(){ refreshNodes().catch(function(){}); refreshJobs().catch(function(){}); refreshTopology().catch(function(){}); }, 800);
    if(document.getElementById('dp').classList.contains('open') && nodeId === node.id){ showNode(nodeId); }
  }catch(err){
    pushEv('job.error', 'discover failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionNodeBootstrap = async function actionNodeBootstrap(nodeId){
  try{
    var node = nById(nodeId);
    var job = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId) + '/bootstrap-runtime', { method:'POST', body:{} });
    pushEv('job.created', 'bootstrap queued for ' + (node.name || nodeId) + ' [' + job.id + ']');
    showToast('Bootstrap queued: ' + (node.name || nodeId) + ' [' + job.id + ']', 'success', 'Job queued');
    await refreshJobs();
    setTimeout(function(){ refreshNodes().catch(function(){}); refreshJobs().catch(function(){}); refreshTopology().catch(function(){}); }, 800);
    if(document.getElementById('dp').classList.contains('open') && nodeId === node.id){ showNode(nodeId); }
  }catch(err){
    pushEv('job.error', 'bootstrap failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionNodeForceReboot = async function actionNodeForceReboot(nodeId){
  if(!confirm('Request immediate node reboot over SSH? For non-root SSH users, passwordless sudo is required.')) return;
  try{
    var node = nById(nodeId);
    var result = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId) + '/force-reboot', { method:'POST', body:{} });
    pushEv('node.reboot_requested', (result && result.message) || ('reboot requested for ' + (node ? node.name : nodeId)));
    showToast('Reboot requested: ' + (node ? node.name : nodeId), 'success', 'Action queued');
    await refreshNodes();
    await refreshTopology();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('node', nodeId)){ showNode(nodeId); }
  }catch(err){
    pushEv('node.reboot.error', 'reboot failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.loadNodeSecurityStatus = async function loadNodeSecurityStatus(nodeId){
  var box = document.getElementById('nodeSecurityBox');
  if(!box) return;
  box.innerHTML = '<div style="color:var(--t1)">Loading node security status…</div>';
  try{
    var summary = await apiFetch(API_PREFIX + '/nodes/' + encodeURIComponent(nodeId) + '/security-status');
    if(!detailContextIs('node', nodeId)) return;
    renderNodeSecurityStatus(summary);
  }catch(err){
    if(!detailContextIs('node', nodeId)) return;
    box.innerHTML = '<div style="color:var(--rd)">' + esc(err && err.message ? err.message : String(err)) + '</div>';
  }
};

window.renderNodeSecurityStatus = function renderNodeSecurityStatus(summary){
  var box = document.getElementById('nodeSecurityBox');
  if(!box || !summary) return;
  var ufwDetail = summary.ufw && summary.ufw.detail ? summary.ufw.detail : '-';
  var fail2banDetail = summary.fail2ban && summary.fail2ban.detail ? summary.fail2ban.detail : '-';
  box.innerHTML =
    '<div class="dp-sep"></div>'
    + '<div style="margin-top:10px;color:var(--t2);font-size:12px;text-transform:uppercase;letter-spacing:.12em;">Security</div>'
    + '<div class="drow"><span class="dk">UFW</span><span class="dv">' + securityFeatureBadge(summary.ufw) + '</span></div>'
    + '<div class="drow"><span class="dk">UFW Detail</span><span class="dv">' + esc(ufwDetail) + '</span></div>'
    + '<div class="drow"><span class="dk">Fail2Ban</span><span class="dv">' + securityFeatureBadge(summary.fail2ban) + '</span></div>'
    + '<div class="drow"><span class="dk">Fail2Ban Detail</span><span class="dv">' + esc(fail2banDetail) + '</span></div>'
    + '<div class="drow"><span class="dk">Checked At</span><span class="dv">' + esc(summary.timestamp ? fmtDateTime(summary.timestamp) : '-') + '</span></div>';
};

window.nodeNetworkTestOptions = function nodeNetworkTestOptions(preferredId){
  var preferred = String(preferredId || '');
  var nodes = NODES.slice().sort(function(a,b){ return String(a.name || '').localeCompare(String(b.name || '')); });
  return nodes.map(function(node){
    var status = String(node.status || '').toLowerCase();
    var label = node.name + (status ? ' (' + status + ')' : '');
    return { value: node.id, label: label };
  });
};

window.openNodeNetworkTestModal = function openNodeNetworkTestModal(sourceNodeId, preset){
  var sourceId = String(sourceNodeId || '');
  var config = preset || {};
  var options = nodeNetworkTestOptions(sourceId);
  if(!options.length){
    showToast('Add at least one node before running network tests.', 'error', 'No nodes');
    return;
  }
  var initialSourceId = options.some(function(opt){ return String(opt.value) === sourceId; }) ? sourceId : options[0].value;
  var initialMode = String(config.mode || 'dns');
  var initialHost = String(config.target_host || 'google.com');
  var initialPort = config.target_port != null ? String(config.target_port) : '';
  var initialDnsServer = String(config.dns_server || '8.8.8.8');
  var initialTimeout = String(config.timeout_seconds || '8');
  var initialCount = String(config.ping_count || '3');
  var initialScheme = String(config.http_scheme || 'https');
  var initialPath = String(config.http_path || '/');
  var body = '<form id="nodeNetworkTestForm"><div class="modal-grid">'
    + formSelect('Source node', 'source_node_id', initialSourceId, options, {help:'Run the test over SSH from this node. Use another node as a temporary test unit.'})
    + formSelect('Mode', 'mode', initialMode, [
        {value:'dns', label:'dns'},
        {value:'ping', label:'ping'},
        {value:'tcp', label:'tcp'},
        {value:'http', label:'http'}
      ])
    + formInput('Target host', 'target_host', initialHost, {required:true, help:'Examples: google.com, 8.8.8.8, your public service host.'})
    + formInput('Target port', 'target_port', initialPort, {type:'number', placeholder:'only for tcp/http'})
    + formInput('DNS server', 'dns_server', initialDnsServer, {placeholder:'8.8.8.8', help:'Used only for DNS tests.'})
    + formInput('Timeout seconds', 'timeout_seconds', initialTimeout, {type:'number'})
    + formInput('Ping count', 'ping_count', initialCount, {type:'number', help:'Used only for ping tests.'})
    + formSelect('HTTP scheme', 'http_scheme', initialScheme, [{value:'https', label:'https'}, {value:'http', label:'http'}])
    + formInput('HTTP path', 'http_path', initialPath, {placeholder:'/'})
    + '</div>'
    + '<div class="mf-help" style="margin-top:10px;">Recommended internet access check: mode <b>dns</b>, target host <b>google.com</b>, DNS server <b>8.8.8.8</b>.</div>'
    + '<div style="display:flex;gap:10px;justify-content:flex-end;margin-top:14px;">'
      + '<button class="btn pri" type="submit">RUN TEST</button>'
    + '</div>'
    + '<div style="margin-top:14px;">'
      + '<label class="mf-label" for="nodeTestResult">Result</label>'
      + '<textarea id="nodeTestResult" class="mf-textarea" readonly style="min-height:260px;">Ready.</textarea>'
    + '</div>'
    + '</form>';
  openModal('Run network test', body);
  bindModalForm('nodeNetworkTestForm', runNodeNetworkTestForm);
};

export {
  nodeInterfaceList,
  renderNodes,
  showNode,
  openNodeModal,
  deleteNodeFlow,
  actionNodeDiscover,
  actionNodeBootstrap,
  actionNodeForceReboot,
  loadNodeSecurityStatus,
  renderNodeSecurityStatus,
  nodeNetworkTestOptions,
  openNodeNetworkTestModal
};
