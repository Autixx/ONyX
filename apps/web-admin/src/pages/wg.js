// Page module - all functions exposed as window globals

window.refreshWgServices = async function refreshWgServices(){
  try{
    var data = await apiFetch(API_PREFIX + '/wg-services');
    WG_SERVICES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!WG_SERVICES.length) WG_SERVICES = [];
  }
  window.renderWgServices();
};

window.renderWgServices = function renderWgServices(){
  var tb = document.getElementById('wgtb');
  if(!tb) return;
  if(!WG_SERVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No WG services.</td></tr>';
    return;
  }
  tb.innerHTML = WG_SERVICES.map(function(service){
    var publicEndpoint = service.public_host + ':' + String(service.public_port || service.listen_port);
    return '<tr onclick="showWgService(\''+esc(service.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(service.name)+'</td>'
      +'<td>'+esc(nById(service.node_id).name)+'</td>'
      +'<td class="m">'+esc(service.interface_name)+'</td>'
      +'<td class="m">'+esc(publicEndpoint)+'</td>'
      +'<td class="m">'+esc(service.server_address_v4 || '-')+'</td>'
      +'<td>'+esc(String(wgPeerCount(service.id)))+'</td>'
      +'<td>'+sp(service.state)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionWgAssignPeer(\''+esc(service.id)+'\')">ASSIGN</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionWgApply(\''+esc(service.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openWgServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteWgServiceFlow(\''+esc(service.id)+'\')">DEL</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.showWgService = function showWgService(id){
  var service = wgServiceById(id);
  if(!service) return;
  var assignedPeers = PEERS.filter(function(peer){ return peer.wg_service_id === service.id && peer.is_active !== false && !peer.revoked_at; });
  var peerRows = assignedPeers.length ? assignedPeers.map(function(peer){
    return '<div class="drow"><span class="dk">'+esc(peer.username || peer.email || peer.id)+'</span><span class="dv">'+esc((peer.wg_address_v4 || '-') + ' / ' + (peer.email || '-'))+'</span></div>';
  }).join('') : '<div class="drow"><span class="dk">No peers</span><span class="dv">-</span></div>';
  var health = service.health_summary_json || {};
  openDP('WG ' + service.name,
    rows([
      ['ID', service.id],
      ['Node', nById(service.node_id).name],
      ['State', service.state || '-'],
      ['Interface', service.interface_name || '-'],
      ['Listen', (service.listen_host || '0.0.0.0') + ':' + String(service.listen_port || '-')],
      ['Public', service.public_host + ':' + String(service.public_port || service.listen_port)],
      ['Server Address', service.server_address_v4 || '-'],
      ['DNS', service.dns_server_v4 || '-'],
      ['MTU', String(service.mtu || '-')],
      ['Keepalive', String(service.persistent_keepalive || '-')],
      ['Config Path', health.config_path || '-'],
      ['Applied At', health.applied_at ? fmtDate(health.applied_at) : '-'],
      ['Peer Count', String(health.peer_count != null ? health.peer_count : assignedPeers.length)],
      ['Server Public Key', service.server_public_key || '-'],
      ['Last Error', service.last_error_text || '-']
    ])
    + '<div class="stitle">Assigned Peers</div>'
    + '<div style="margin-top:8px;">' + peerRows + '</div>'
    + '<div class="dp-actions">'
      +'<button class="btn" onclick="actionWgAssignPeer(\''+esc(service.id)+'\')">ASSIGN PEER</button>'
      +'<button class="btn pri" onclick="actionWgApply(\''+esc(service.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openWgServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteWgServiceFlow(\''+esc(service.id)+'\')">DELETE</button>'
    +'</div>'
  );
};

window.openWgServiceModal = function openWgServiceModal(serviceId){
  var service = serviceId ? wgServiceById(serviceId) : null;
  var nodeOptions = NODES.map(function(node){ return {value:node.id, label:node.name}; });
  var body = '<form id="wgServiceForm"><div class="modal-grid">'
    +formInput('Name', 'name', service ? service.name : '', {required:true})
    +formSelect('Node', 'node_id', service ? service.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions, {help:'Managed node where WG will run.'})
    +formInput('Interface', 'interface_name', service ? service.interface_name : 'wg0', {required:true})
    +formInput('Listen port', 'listen_port', service ? String(service.listen_port) : '51820', {type:'number', required:true})
    +formInput('Public host', 'public_host', service ? service.public_host : '', {required:true})
    +formInput('Public port', 'public_port', service && service.public_port != null ? String(service.public_port) : '', {type:'number'})
    +formInput('Server address', 'server_address_v4', service ? service.server_address_v4 : '10.251.0.1/24', {required:true})
    +formInput('DNS server', 'dns_server_v4', service ? (service.dns_server_v4 || '') : '')
    +formInput('MTU', 'mtu', service ? String(service.mtu) : '1420', {type:'number'})
    +formInput('Keepalive', 'persistent_keepalive', service ? String(service.persistent_keepalive) : '25', {type:'number'})
    +formTextarea('Client allowed IPs', 'client_allowed_ips_json', service ? (service.client_allowed_ips_json || []).join(', ') : '0.0.0.0/0, ::/0', {help:'Comma-separated CIDRs.'})
    +'</div></form>';
  openModal(service ? 'Edit service' : 'Create service', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:service ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('wgServiceForm').requestSubmit(); }}
    ]
  });
  bindNodeHostAutofill('wgServiceForm', 'node_id', 'public_host');
  bindModalForm('wgServiceForm', function(fd){ saveWgServiceForm(fd, serviceId); });
};

window.deleteWgServiceFlow = async function deleteWgServiceFlow(serviceId){
  var service = wgServiceById(serviceId);
  if(!confirm('Delete WG service ' + (service ? service.name : serviceId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/wg-services/' + encodeURIComponent(serviceId), { method:'DELETE' });
    pushEv('wg_service.deleted', 'WG service deleted: ' + (service ? service.name : serviceId));
    await refreshWgServices();
    closeDP();
  }catch(err){
    pushEv('wg_service.error', 'delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionWgApply = async function actionWgApply(serviceId){
  try{
    var service = wgServiceById(serviceId);
    var applied = await apiFetch(API_PREFIX + '/wg-services/' + encodeURIComponent(serviceId) + '/apply', { method:'POST', body:{} });
    pushEv('wg_service.applied', 'WG service applied: ' + ((applied && applied.name) || (service && service.name) || serviceId));
    await Promise.all([refreshWgServices(), loadPeers()]);
    if(service){ window.showWgService(serviceId); }
  }catch(err){
    pushEv('wg_service.error', 'apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionWgAssignPeer = async function actionWgAssignPeer(serviceId){
  var service = wgServiceById(serviceId);
  if(!service) return;
  if(!PEERS.length){ await loadPeers(); }
  var peerOptions = PEERS.filter(function(peer){ return peer.is_active !== false && !peer.revoked_at; }).map(function(peer){
    return {value: peer.id, label: (peer.username || peer.email || peer.id) + ' — ' + (peer.email || 'no-email')};
  });
  if(!peerOptions.length){ alert('No active peers available.'); return; }
  var body = '<form id="wgAssignPeerForm"><div class="modal-grid">'
    +formSelect('Peer', 'peer_id', peerOptions[0].value, peerOptions, {full:true})
    +formCheckbox('Save config to peer', 'save_to_peer', true, {caption:'Persist generated client config to peer record', full:true})
    +'</div></form>';
  openModal('Assign Peer — ' + service.name, body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Assign', className:'btn pri', onClick:function(){ document.getElementById('wgAssignPeerForm').requestSubmit(); }}
    ]
  });
  bindModalForm('wgAssignPeerForm', function(fd){ submitWgAssignPeer(serviceId, fd); });
};

export { refreshWgServices, renderWgServices, showWgService, openWgServiceModal, deleteWgServiceFlow, actionWgApply, actionWgAssignPeer };
