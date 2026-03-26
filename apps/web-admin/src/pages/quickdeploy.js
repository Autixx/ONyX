// Quick Deploy page module

if(typeof window._quickDeployWatchTimer === 'undefined'){
  window._quickDeployWatchTimer = null;
}
if(typeof window._quickDeployWatchedSessionId === 'undefined'){
  window._quickDeployWatchedSessionId = null;
}
if(typeof window._quickDeployTicker === 'undefined'){
  window._quickDeployTicker = null;
}

window.quickDeployScenarioLabel = function quickDeployScenarioLabel(value){
  if(value === 'gate_egress') return 'gate-egress';
  return value || '-';
};

window.quickDeployStateBadge = function quickDeployStateBadge(state){
  return window.sp ? window.sp(state || '-') : window.esc(state || '-');
};

window.quickDeployNodesLabel = function quickDeployNodesLabel(session){
  var resources = session && session.resources_json ? session.resources_json : {};
  var gate = resources.gate_node_name || resources.gate_node_id || '-';
  var egress = resources.egress_node_name || resources.egress_node_id || '-';
  return gate + ' -> ' + egress;
};

window.quickDeployJobCount = function quickDeployJobCount(session){
  return Array.isArray(session && session.child_jobs) ? session.child_jobs.length : 0;
};

window.renderQuickDeploySessions = function renderQuickDeploySessions(){
  var tb = document.getElementById('qdtb');
  if(!tb) return;
  if(!window.QUICK_DEPLOY_SESSIONS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No quick deploy sessions.</td></tr>';
    return;
  }
  tb.innerHTML = window.QUICK_DEPLOY_SESSIONS.map(function(session){
    var canCancel = session.state === 'planned' || session.state === 'running';
    return '<tr onclick="openQuickDeployModal(\''+window.esc(session.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+window.esc(session.id)+'</td>'
      +'<td class="m">'+window.esc(window.quickDeployScenarioLabel(session.scenario))+'</td>'
      +'<td>'+window.esc(window.quickDeployNodesLabel(session))+'</td>'
      +'<td class="m">'+window.esc(session.current_stage || '-')+'</td>'
      +'<td>'+window.quickDeployStateBadge(session.state)+'</td>'
      +'<td class="m">'+window.esc(String(window.quickDeployJobCount(session)))+'</td>'
      +'<td class="m">'+window.esc(window.fmtDate(session.updated_at))+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openQuickDeployModal(\''+window.esc(session.id)+'\')">OPEN</button>'
        +(canCancel ? '<button class="btn sm red" onclick="event.stopPropagation();cancelQuickDeploySessionFlow(\''+window.esc(session.id)+'\')">CANCEL</button>' : '')
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.refreshQuickDeploySessions = async function refreshQuickDeploySessions(){
  try{
    var data = await apiFetch(API_PREFIX + '/quick-deploy/sessions');
    window.QUICK_DEPLOY_SESSIONS = Array.isArray(data) ? data : [];
  }catch(err){
    if(!window.QUICK_DEPLOY_SESSIONS.length) window.QUICK_DEPLOY_SESSIONS = [];
  }
  window.renderQuickDeploySessions();
  return window.QUICK_DEPLOY_SESSIONS;
};

window.refreshQuickDeploySession = async function refreshQuickDeploySession(sessionId){
  var session = await apiFetch(API_PREFIX + '/quick-deploy/sessions/' + encodeURIComponent(sessionId));
  var idx = window.QUICK_DEPLOY_SESSIONS.findIndex(function(item){ return item.id === session.id; });
  if(idx >= 0) window.QUICK_DEPLOY_SESSIONS[idx] = session;
  else window.QUICK_DEPLOY_SESSIONS.unshift(session);
  window.renderQuickDeploySessions();
  return session;
};

window.quickDeployFormBody = function quickDeployFormBody(){
  var scenarioOptions = [
    {value:'gate_egress', label:'gate-egress'},
  ];
  var clientTransportOptions = [
    {value:'awg', label:'AWG'},
  ];
  var egressTransportOptions = [
    {value:'xray_vless_xhttp_reality', label:'XRAY VLESS xHTTP REALITY'},
  ];
  return '<form id="quickDeployForm">'
    +'<div class="stitle">Deployment</div>'
    +'<div class="modal-grid">'
      +window.formSelect('Scenario', 'scenario', 'gate_egress', scenarioOptions, {help:'Current MVP only supports gate-egress.'})
      +window.formSelect('Client transport', 'gate_client_transport', 'awg', clientTransportOptions, {help:'Gate-side client entrypoint.'})
      +window.formSelect('Egress transport', 'egress_transport', 'xray_vless_xhttp_reality', egressTransportOptions, {help:'Gate -> egress method.'})
    +'</div>'
    +'<div class="stitle">Gate Node</div>'
    +'<div class="modal-grid">'
      +window.formInput('Gate host', 'gate_host', '', {required:true, help:'Used as SSH host and management address.'})
      +window.formInput('Gate node name', 'gate_node_name', '', {placeholder:'auto'})
      +window.formInput('Gate SSH user', 'gate_ssh_user', 'root', {required:true})
      +window.formInput('Gate SSH port', 'gate_ssh_port', '22', {required:true, type:'number'})
      +window.formSelect('Gate auth type', 'gate_auth_type', 'password', [
        {value:'password', label:'password'},
        {value:'private_key', label:'private_key'}
      ])
      +window.formTextarea('Gate secret', 'gate_secret', '', {help:'SSH password or private key.', full:true})
    +'</div>'
    +'<div class="stitle">Egress Node</div>'
    +'<div class="modal-grid">'
      +window.formInput('Egress host', 'egress_host', '', {required:true, help:'Used as SSH host and management address.'})
      +window.formInput('Egress node name', 'egress_node_name', '', {placeholder:'auto'})
      +window.formInput('Egress SSH user', 'egress_ssh_user', 'root', {required:true})
      +window.formInput('Egress SSH port', 'egress_ssh_port', '22', {required:true, type:'number'})
      +window.formSelect('Egress auth type', 'egress_auth_type', 'password', [
        {value:'password', label:'password'},
        {value:'private_key', label:'private_key'}
      ])
      +window.formTextarea('Egress secret', 'egress_secret', '', {help:'SSH password or private key.', full:true})
    +'</div>'
    +'<div class="stitle">Gate Client Service</div>'
    +'<div class="modal-grid">'
      +window.formInput('AWG interface', 'gate_client_interface_name', 'awg0', {required:true})
      +window.formInput('AWG listen port', 'gate_client_listen_port', '8443', {required:true, type:'number'})
      +window.formInput('Server address v4', 'gate_client_server_address_v4', '10.250.0.1/24', {required:true})
    +'</div>'
    +'<div class="stitle">Egress XRAY</div>'
    +'<div class="modal-grid">'
      +window.formInput('Reality server name', 'egress_server_name', 'nos.nl', {required:true})
      +window.formInput('xHTTP path', 'egress_xhttp_path', '/news', {required:true})
      +window.formInput('Listen/public port', 'egress_listen_port', '443', {required:true, type:'number'})
      +window.formInput('Transit transparent port', 'transit_transparent_port', '15001', {required:true, type:'number'})
    +'</div>'
    +'</form>';
};

window.openQuickDeployModal = function openQuickDeployModal(sessionId){
  if(sessionId){
    window.openQuickDeploySessionMonitor(sessionId);
    return;
  }
  window.openModal('Quick Deploy', window.quickDeployFormBody(), {
    buttons:[
      {label:'Cancel', className:'btn', onClick:window.closeModal},
      {label:'Start Deploy', className:'btn pri', onClick:function(){
        var form = document.getElementById('quickDeployForm');
        if(form) form.requestSubmit();
      }}
    ]
  });
  var gateSecretEl = document.getElementById('gate_secret');
  var egressSecretEl = document.getElementById('egress_secret');
  if(gateSecretEl) gateSecretEl.setAttribute('required', 'required');
  if(egressSecretEl) egressSecretEl.setAttribute('required', 'required');
  window.bindModalForm('quickDeployForm', function(fd){ window.submitQuickDeployForm(fd); });
};

window.submitQuickDeployForm = async function submitQuickDeployForm(fd){
  function intField(name, fallback){
    var raw = String(fd.get(name) == null ? '' : fd.get(name)).trim();
    var parsed = parseInt(raw, 10);
    return isNaN(parsed) ? fallback : parsed;
  }
  function textField(name){
    return String(fd.get(name) == null ? '' : fd.get(name)).trim();
  }
  var payload = {
    scenario: textField('scenario') || 'gate_egress',
    gate_node_name: textField('gate_node_name') || null,
    gate_host: textField('gate_host'),
    gate_ssh_port: intField('gate_ssh_port', 22),
    gate_ssh_user: textField('gate_ssh_user') || 'root',
    gate_auth_type: textField('gate_auth_type') || 'password',
    gate_secret: String(fd.get('gate_secret') || ''),
    egress_node_name: textField('egress_node_name') || null,
    egress_host: textField('egress_host'),
    egress_ssh_port: intField('egress_ssh_port', 22),
    egress_ssh_user: textField('egress_ssh_user') || 'root',
    egress_auth_type: textField('egress_auth_type') || 'password',
    egress_secret: String(fd.get('egress_secret') || ''),
    gate_client_transport: textField('gate_client_transport') || 'awg',
    egress_transport: textField('egress_transport') || 'xray_vless_xhttp_reality',
    egress_server_name: textField('egress_server_name') || 'nos.nl',
    egress_xhttp_path: textField('egress_xhttp_path') || '/news',
    egress_listen_port: intField('egress_listen_port', 443),
    gate_client_listen_port: intField('gate_client_listen_port', 8443),
    gate_client_interface_name: textField('gate_client_interface_name') || 'awg0',
    gate_client_server_address_v4: textField('gate_client_server_address_v4') || '10.250.0.1/24',
    transit_transparent_port: intField('transit_transparent_port', 15001),
  };
  try{
    var session = await apiFetch(API_PREFIX + '/quick-deploy/sessions', {method:'POST', body:payload});
    await window.refreshQuickDeploySessions();
    window.showToast?.('Quick deploy queued.', 'success', 'Quick Deploy');
    window.openQuickDeploySessionMonitor(session.id);
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.quickDeployMonitorBody = function quickDeployMonitorBody(session){
  var jobs = Array.isArray(session && session.child_jobs) ? session.child_jobs : [];
  var jobsHtml = jobs.length ? jobs.map(function(entry){
    var job = entry.job || {};
    return '<tr>'
      +'<td class="m">'+window.esc(entry.step || '-')+'</td>'
      +'<td class="m">'+window.esc(job.kind || '-')+'</td>'
      +'<td class="m">'+window.esc((job.target_type || '-') + ':' + (job.target_id || '-'))+'</td>'
      +'<td>'+window.quickDeployStateBadge(job.state || '-')
        +(job.error_text ? '<div class="mf-help" style="margin-top:4px;color:var(--red);">'+window.esc(job.error_text)+'</div>' : '')
      +'</td>'
      +'</tr>';
  }).join('') : '<tr><td class="empty-state" colspan="4">Waiting for first job.</td></tr>';
  return '<div class="tw" style="margin-bottom:14px;padding:14px 16px;color:var(--t1);line-height:1.55;">'
      +'<div class="drow"><span class="dk">Scenario</span><span class="dv">'+window.esc(window.quickDeployScenarioLabel(session.scenario))+'</span></div>'
      +'<div class="drow"><span class="dk">Nodes</span><span class="dv">'+window.esc(window.quickDeployNodesLabel(session))+'</span></div>'
      +'<div class="drow"><span class="dk">State</span><span class="dv">'+window.quickDeployStateBadge(session.state)+'</span></div>'
      +'<div class="drow"><span class="dk">Current stage</span><span class="dv">'+window.esc(session.current_stage || '-')+'</span></div>'
      +'<div class="drow"><span class="dk">Created</span><span class="dv">'+window.esc(window.fmtDate(session.created_at))+'</span></div>'
      +'<div class="drow"><span class="dk">Updated</span><span class="dv">'+window.esc(window.fmtDate(session.updated_at))+'</span></div>'
      +(session.error_text ? '<div class="drow"><span class="dk">Error</span><span class="dv" style="color:var(--red)">'+window.esc(session.error_text)+'</span></div>' : '')
    +'</div>'
    +'<div class="stitle">Stage Jobs</div>'
    +'<div class="tw"><table><thead><tr><th>Step</th><th>Kind</th><th>Target</th><th>State</th></tr></thead><tbody>'+jobsHtml+'</tbody></table></div>';
};

window.quickDeployRenderMonitor = function quickDeployRenderMonitor(session){
  var titleEl = document.getElementById('modalTitle');
  var bodyEl = document.getElementById('modalBody');
  var actionsEl = document.getElementById('modalActions');
  if(!titleEl || !bodyEl || !actionsEl) return;
  titleEl.textContent = 'Quick Deploy Monitor';
  bodyEl.innerHTML = window.quickDeployMonitorBody(session);
  actionsEl.innerHTML = '';
  var closeBtn = document.createElement('button');
  closeBtn.className = 'btn';
  closeBtn.type = 'button';
  closeBtn.textContent = 'Close';
  closeBtn.addEventListener('click', window.closeModal);
  actionsEl.appendChild(closeBtn);
  if(session.state === 'planned' || session.state === 'running'){
    var cancelBtn = document.createElement('button');
    cancelBtn.className = 'btn red';
    cancelBtn.type = 'button';
    cancelBtn.textContent = 'Cancel Deploy';
    cancelBtn.addEventListener('click', function(){ window.cancelQuickDeploySessionFlow(session.id); });
    actionsEl.appendChild(cancelBtn);
  }
  window.scheduleLocaleRefresh?.();
};

window.stopQuickDeployWatch = function stopQuickDeployWatch(){
  if(window._quickDeployWatchTimer){
    clearInterval(window._quickDeployWatchTimer);
    window._quickDeployWatchTimer = null;
  }
  window._quickDeployWatchedSessionId = null;
};

window.openQuickDeploySessionMonitor = async function openQuickDeploySessionMonitor(sessionId){
  try{
    var session = window.quickDeploySessionById(sessionId) || await window.refreshQuickDeploySession(sessionId);
    window.openModal('Quick Deploy Monitor', window.quickDeployMonitorBody(session), {
      buttons:[{label:'Close', className:'btn', onClick:window.closeModal}]
    });
    window.quickDeployRenderMonitor(session);
    window.stopQuickDeployWatch();
    window._quickDeployWatchedSessionId = session.id;
    if(session.state === 'ready' || session.state === 'failed' || session.state === 'cancelled'){
      return;
    }
    window._quickDeployWatchTimer = setInterval(async function(){
      if(!window._quickDeployWatchedSessionId){
        window.stopQuickDeployWatch();
        return;
      }
      if(!document.getElementById('modal').classList.contains('open')){
        window.stopQuickDeployWatch();
        return;
      }
      try{
        var fresh = await window.refreshQuickDeploySession(window._quickDeployWatchedSessionId);
        window.quickDeployRenderMonitor(fresh);
        if(fresh.state === 'ready' || fresh.state === 'failed' || fresh.state === 'cancelled'){
          if(fresh.state === 'ready'){
            window.showToast?.('Deployment is ready.', 'success', 'Quick Deploy');
          }
          window.stopQuickDeployWatch();
        }
      }catch(_){
      }
    }, 2000);
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.cancelQuickDeploySessionFlow = async function cancelQuickDeploySessionFlow(sessionId){
  if(!confirm('Cancel quick deploy session ' + sessionId + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/quick-deploy/sessions/' + encodeURIComponent(sessionId) + '/cancel', {method:'POST', body:{}});
    var session = await window.refreshQuickDeploySession(sessionId);
    if(window._quickDeployWatchedSessionId === sessionId && document.getElementById('modal').classList.contains('open')){
      window.quickDeployRenderMonitor(session);
    }
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.startQuickDeployTicker = function startQuickDeployTicker(){
  if(window._quickDeployTicker) clearInterval(window._quickDeployTicker);
  window._quickDeployTicker = setInterval(function(){
    var hasActive = (window.QUICK_DEPLOY_SESSIONS || []).some(function(session){
      return session && (session.state === 'planned' || session.state === 'running');
    });
    if(hasActive || window.CURRENT_PAGE === 'quickdeploy'){
      window.refreshQuickDeploySessions?.().catch(function(){});
    }
  }, 5000);
};

document.addEventListener('DOMContentLoaded', function(){
  window.startQuickDeployTicker();
});

export {};
