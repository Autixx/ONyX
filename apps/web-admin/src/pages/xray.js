// Page module - all functions exposed as window globals

window.xrayPeerCount = function xrayPeerCount(serviceId){
  return PEERS.filter(function(p){ return p.xray_service_id === serviceId && p.is_active !== false && !p.revoked_at; }).length;
};

window.refreshXrayServices = async function refreshXrayServices(){
  try{
    var data = await apiFetch(API_PREFIX + '/xray-services');
    XRAY_SERVICES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!XRAY_SERVICES.length) XRAY_SERVICES = [];
  }
  window.renderXrayServices();
  renderTransitPolicies();
  renderPolicyTransitHub();
};

window.renderXrayServices = function renderXrayServices(){
  var tb = document.getElementById('xraytb');
  if(!tb) return;
  if(!XRAY_SERVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No XRAY services.</td></tr>';
    return;
  }
  tb.innerHTML = XRAY_SERVICES.map(function(service){
    var publicEndpoint = service.public_host + ':' + String(service.public_port || service.listen_port);
    var security = service.reality_enabled
      ? '<span class="pill pb">reality</span>'
      : (service.tls_enabled ? '<span class="pill pg">tls</span>' : '<span class="pill pq">plain</span>');
    return '<tr onclick="showXrayService(\''+esc(service.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(service.name)+'</td>'
      +'<td>'+esc(nById(service.node_id).name)+'</td>'
      +'<td class="m">'+esc(publicEndpoint)+'</td>'
      +'<td class="m">'+esc(service.xhttp_path || '/')+'</td>'
      +'<td>'+security+'</td>'
      +'<td>'+esc(String(xrayPeerCount(service.id)))+'</td>'
      +'<td>'+sp(service.state)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionXrayAssignPeer(\''+esc(service.id)+'\')">ASSIGN</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openXrayTransitWizard(\''+esc(service.id)+'\')">GUIDE</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionXrayApply(\''+esc(service.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openXrayServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteXrayServiceFlow(\''+esc(service.id)+'\')">DEL</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.showXrayService = function showXrayService(id){
  var service = xrayServiceById(id);
  if(!service) return;
  var assignedPeers = PEERS.filter(function(peer){ return peer.xray_service_id === service.id && peer.is_active !== false && !peer.revoked_at; });
  var peerRows = assignedPeers.length ? assignedPeers.map(function(peer){
    return '<div class="drow"><span class="dk">'+esc(peer.username || peer.email || peer.id)+'</span><span class="dv">'+esc(peer.email || '-')+'</span></div>';
  }).join('') : '<div class="drow"><span class="dk">No peers</span><span class="dv">-</span></div>';
  var health = service.health_summary_json || {};
  openDP('XRAY ' + service.name,
    rows([
      ['ID', service.id],
      ['Node', nById(service.node_id).name],
      ['Transport', service.transport_mode || '-'],
      ['State', service.state || '-'],
      ['Listen', (service.listen_host || '0.0.0.0') + ':' + String(service.listen_port || '-')],
      ['Public', service.public_host + ':' + String(service.public_port || service.listen_port)],
      ['Server Name', service.server_name || '-'],
      ['Path', service.xhttp_path || '/'],
      ['Security', service.reality_enabled ? 'reality' : (service.tls_enabled ? 'tls' : 'plain')],
      ['REALITY Dest', service.reality_dest || '-'],
      ['REALITY Short ID', service.reality_short_id || '-'],
      ['REALITY Public Key', service.reality_public_key || '-'],
      ['REALITY Fingerprint', service.reality_fingerprint || '-'],
      ['REALITY SpiderX', service.reality_spider_x || '-'],
      ['Transit Policies', String(transitServiceCount(service.id))],
      ['Config Path', health.config_path || '-'],
      ['Applied At', health.applied_at ? fmtDate(health.applied_at) : '-'],
      ['Peer Count', String(health.peer_count != null ? health.peer_count : assignedPeers.length)],
      ['Last Error', service.last_error_text || '-']
    ])
    + '<div class="stitle">Assigned Peers</div>'
    + '<div style="margin-top:8px;">' + peerRows + '</div>'
    + '<div class="stitle">Transit Policies</div>'
    + '<div style="margin-top:8px;">'
      + (transitPoliciesForXray(service.id).length
          ? transitPoliciesForXray(service.id).map(function(policy){
              return '<div class="drow"><span class="dk">'+esc(policy.name)+'</span><span class="dv">'+esc(transitNextHopSummary(policy))+' / '+esc(policy.state || '-')+'</span></div>';
            }).join('')
          : '<div class="drow"><span class="dk">No transit policies</span><span class="dv">-</span></div>')
    + '</div>'
    + '<div class="dp-actions">'
      +'<button class="btn" onclick="actionXrayAssignPeer(\''+esc(service.id)+'\')">ASSIGN PEER</button>'
      +'<button class="btn" onclick="openXrayTransitWizard(\''+esc(service.id)+'\')">ATTACH NEXT HOP</button>'
      +'<button class="btn" onclick="openTransitPolicyModal(null,\''+esc(service.id)+'\')">ADVANCED TRANSIT</button>'
      +'<button class="btn pri" onclick="actionXrayApply(\''+esc(service.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openXrayServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteXrayServiceFlow(\''+esc(service.id)+'\')">DELETE</button>'
    +'</div>'
  );
};

window.openXrayServiceModal = function openXrayServiceModal(serviceId){
  var service = serviceId ? xrayServiceById(serviceId) : null;
  var nodeOptions = NODES.map(function(node){ return {value:node.id, label:node.name}; });
  var body = '<form id="xrayServiceForm"><div class="modal-grid">'
    +formInput('Name', 'name', service ? service.name : '', {required:true})
    +formSelect('Node', 'node_id', service ? service.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions, {help:'Managed node where xray will run.'})
    +formInput('Listen host', 'listen_host', service ? service.listen_host : '0.0.0.0', {required:true})
    +formInput('Listen port', 'listen_port', service ? String(service.listen_port) : '443', {type:'number', required:true})
    +formInput('Public host', 'public_host', service ? service.public_host : '', {required:true})
    +formInput('Public port', 'public_port', service && service.public_port != null ? String(service.public_port) : '', {type:'number'})
    +formInput('Server name', 'server_name', service ? (service.server_name || '') : '')
    +formInput('xHTTP path', 'xhttp_path', service ? (service.xhttp_path || '/') : '/', {required:true})
    +formCheckbox('TLS enabled', 'tls_enabled', service ? !!service.tls_enabled : false, {caption:'Use TLS stream security'})
    +formCheckbox('REALITY enabled', 'reality_enabled', service ? !!service.reality_enabled : false, {caption:'Use REALITY instead of plain/TLS'})
    +formInput('REALITY dest', 'reality_dest', service ? (service.reality_dest || '') : '', {placeholder:'nos.nl:443'})
    +formInput('REALITY short id', 'reality_short_id', service ? (service.reality_short_id || '') : '', {placeholder:'auto'})
    +formInput('REALITY fingerprint', 'reality_fingerprint', service ? (service.reality_fingerprint || '') : 'chrome')
    +formInput('REALITY spiderX', 'reality_spider_x', service ? (service.reality_spider_x || '/') : '/')
    +formTextarea('REALITY public key', 'reality_public_key', service ? (service.reality_public_key || '') : '', {help:'Optional. Leave empty for auto-generated pair.'})
    +formTextarea('REALITY private key', 'reality_private_key', service ? '' : '', {help:'Optional. Leave empty for auto-generated pair. Existing value is hidden on read.'})
    +'</div></form>';
  openModal(service ? 'Edit service' : 'Create service', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:service ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('xrayServiceForm').requestSubmit(); }}
    ]
  });
  bindNodeHostAutofill('xrayServiceForm', 'node_id', 'public_host');
  bindModalForm('xrayServiceForm', function(fd){ saveXrayServiceForm(fd, serviceId); });
};

window.saveXrayServiceForm = async function saveXrayServiceForm(fd, serviceId){
  function intField(v){ var n = parseInt(v, 10); return isNaN(n) ? null : n; }
  try{
    if(serviceId){
      var patch = {};
      ['name','node_id','listen_host','xhttp_path'].forEach(function(k){
        var v = fd.get(k); if(v != null) patch[k] = v;
      });
      var lp = intField(fd.get('listen_port')); if(lp != null) patch.listen_port = lp;
      var ph = fd.get('public_host'); if(ph) patch.public_host = ph;
      var pp = intField(fd.get('public_port')); if(pp != null) patch.public_port = pp;
      var sn = (fd.get('server_name') || '').trim(); if(sn) patch.server_name = sn;
      var rd = (fd.get('reality_dest') || '').trim(); if(rd) patch.reality_dest = rd;
      var rfp = (fd.get('reality_fingerprint') || '').trim(); if(rfp) patch.reality_fingerprint = rfp;
      var rsx = (fd.get('reality_spider_x') || '').trim(); if(rsx) patch.reality_spider_x = rsx;
      patch.tls_enabled = fd.get('tls_enabled') === 'on';
      patch.reality_enabled = fd.get('reality_enabled') === 'on';
      var rsid = (fd.get('reality_short_id') || '').trim(); if(rsid) patch.reality_short_id = rsid;
      var rpk = (fd.get('reality_public_key') || '').trim(); if(rpk) patch.reality_public_key = rpk;
      var rsk = (fd.get('reality_private_key') || '').trim(); if(rsk) patch.reality_private_key = rsk;
      await apiFetch(API_PREFIX+'/xray-services/'+encodeURIComponent(serviceId), {method:'PATCH', body:patch});
    }else{
      var payload = {
        name: fd.get('name'),
        node_id: fd.get('node_id'),
        listen_host: fd.get('listen_host') || '0.0.0.0',
        listen_port: intField(fd.get('listen_port')),
        public_host: fd.get('public_host'),
        xhttp_path: fd.get('xhttp_path') || '/',
        tls_enabled: fd.get('tls_enabled') === 'on',
        reality_enabled: fd.get('reality_enabled') === 'on'
      };
      var pp = intField(fd.get('public_port')); if(pp != null) payload.public_port = pp;
      var sn = (fd.get('server_name') || '').trim(); if(sn) payload.server_name = sn;
      var rd = (fd.get('reality_dest') || '').trim(); if(rd) payload.reality_dest = rd;
      var rsid = (fd.get('reality_short_id') || '').trim(); if(rsid) payload.reality_short_id = rsid;
      var rfp = (fd.get('reality_fingerprint') || '').trim(); if(rfp) payload.reality_fingerprint = rfp;
      var rsx = (fd.get('reality_spider_x') || '').trim(); if(rsx) payload.reality_spider_x = rsx;
      var rpk = (fd.get('reality_public_key') || '').trim(); if(rpk) payload.reality_public_key = rpk;
      var rsk = (fd.get('reality_private_key') || '').trim(); if(rsk) payload.reality_private_key = rsk;
      await apiFetch(API_PREFIX+'/xray-services', {method:'POST', body:payload});
    }
    closeModal();
    await refreshXrayServices();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.deleteXrayServiceFlow = async function deleteXrayServiceFlow(serviceId){
  var service = xrayServiceById(serviceId);
  if(!confirm('Delete XRAY service ' + (service ? service.name : serviceId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/xray-services/' + encodeURIComponent(serviceId), { method:'DELETE' });
    pushEv('xray_service.deleted', 'XRAY service deleted: ' + (service ? service.name : serviceId));
    await refreshXrayServices();
    closeDP();
  }catch(err){
    pushEv('xray_service.error', 'delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionXrayApply = async function actionXrayApply(serviceId){
  try{
    var service = xrayServiceById(serviceId);
    var applied = await apiFetch(API_PREFIX + '/xray-services/' + encodeURIComponent(serviceId) + '/apply', { method:'POST', body:{} });
    pushEv('xray_service.applied', 'XRAY service applied: ' + ((applied && applied.name) || (service && service.name) || serviceId));
    await Promise.all([refreshXrayServices(), loadPeers()]);
    if(service){ window.showXrayService(serviceId); }
  }catch(err){
    pushEv('xray_service.error', 'apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.openXrayTransitWizard = function openXrayTransitWizard(serviceId){
  openTransitPolicyModal(null, serviceId);
};

window.actionXrayAssignPeer = async function actionXrayAssignPeer(serviceId){
  var service = xrayServiceById(serviceId);
  if(!service) return;
  if(!PEERS.length){
    await loadPeers();
  }
  var peerOptions = PEERS
    .filter(function(peer){ return peer.is_active !== false && !peer.revoked_at; })
    .map(function(peer){
      return {value: peer.id, label: (peer.username || peer.email || peer.id) + ' — ' + (peer.email || 'no-email')};
    });
  if(!peerOptions.length){
    alert('No active peers available.');
    return;
  }
  var body = '<form id="xrayAssignPeerForm"><div class="modal-grid">'
    +formSelect('Peer', 'peer_id', peerOptions[0].value, peerOptions, {full:true})
    +formCheckbox('Save config to peer', 'save_to_peer', true, {caption:'Persist generated client config to peer record', full:true})
    +'</div></form>';
  openModal('Assign Peer — ' + service.name, body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Assign', className:'btn pri', onClick:function(){ document.getElementById('xrayAssignPeerForm').requestSubmit(); }}
    ]
  });
  bindModalForm('xrayAssignPeerForm', function(fd){ submitXrayAssignPeer(serviceId, fd); });
};

export {};
