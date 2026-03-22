// Page module - all functions exposed as window globals

window.refreshOpenvpnCloakServices = async function refreshOpenvpnCloakServices(){
  try{
    var data = await apiFetch(API_PREFIX + '/openvpn-cloak-services');
    OVPN_CLOAK_SERVICES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!OVPN_CLOAK_SERVICES.length) OVPN_CLOAK_SERVICES = [];
  }
  window.renderOpenvpnCloakServices();
};

window.renderOpenvpnCloakServices = function renderOpenvpnCloakServices(){
  var tb = document.getElementById('ovpntb');
  if(!tb) return;
  if(!OVPN_CLOAK_SERVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="9">No OpenVPN+Cloak services.</td></tr>';
    return;
  }
  tb.innerHTML = OVPN_CLOAK_SERVICES.map(function(service){
    var publicEndpoint = service.public_host + ':' + String(service.public_port || service.cloak_listen_port);
    var openvpnEndpoint = (service.openvpn_local_host || '127.0.0.1') + ':' + String(service.openvpn_local_port || '-');
    var cloakListen = (service.cloak_listen_host || '0.0.0.0') + ':' + String(service.cloak_listen_port || '-');
    return '<tr onclick="showOpenvpnCloakService(\''+esc(service.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(service.name)+'</td>'
      +'<td>'+esc(nById(service.node_id).name)+'</td>'
      +'<td class="m">'+esc(openvpnEndpoint)+'</td>'
      +'<td class="m">'+esc(cloakListen)+'</td>'
      +'<td class="m">'+esc(publicEndpoint)+'</td>'
      +'<td class="m">'+esc(service.server_network_v4 || '-')+'</td>'
      +'<td>'+esc(String(openvpnCloakPeerCount(service.id)))+'</td>'
      +'<td>'+sp(service.state)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionOpenvpnCloakAssignPeer(\''+esc(service.id)+'\')">ASSIGN</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionOpenvpnCloakApply(\''+esc(service.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openOpenvpnCloakServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteOpenvpnCloakServiceFlow(\''+esc(service.id)+'\')">DEL</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.showOpenvpnCloakService = function showOpenvpnCloakService(id){
  var service = openvpnCloakServiceById(id);
  if(!service) return;
  var assignedPeers = PEERS.filter(function(peer){ return peer.openvpn_cloak_service_id === service.id && peer.is_active !== false && !peer.revoked_at; });
  var peerRows = assignedPeers.length ? assignedPeers.map(function(peer){
    return '<div class="drow"><span class="dk">'+esc(peer.username || peer.email || peer.id)+'</span><span class="dv">'+esc((peer.cloak_uid || '-') + ' / ' + (peer.email || '-'))+'</span></div>';
  }).join('') : '<div class="drow"><span class="dk">No peers</span><span class="dv">-</span></div>';
  var health = service.health_summary_json || {};
  openDP('OpenVPN+Cloak ' + service.name,
    rows([
      ['ID', service.id],
      ['Node', nById(service.node_id).name],
      ['State', service.state || '-'],
      ['OpenVPN', (service.openvpn_local_host || '127.0.0.1') + ':' + String(service.openvpn_local_port || '-')],
      ['Cloak Listen', (service.cloak_listen_host || '0.0.0.0') + ':' + String(service.cloak_listen_port || '-')],
      ['Public', service.public_host + ':' + String(service.public_port || service.cloak_listen_port)],
      ['Server Name', service.server_name || '-'],
      ['Client Local Port', String(service.client_local_port || '-')],
      ['Server Network', service.server_network_v4 || '-'],
      ['DNS', service.dns_server_v4 || '-'],
      ['MTU', String(service.mtu || '-')],
      ['OpenVPN Config Path', health.openvpn_conf_path || '-'],
      ['Cloak Config Path', health.cloak_conf_path || '-'],
      ['Applied At', health.applied_at ? fmtDate(health.applied_at) : '-'],
      ['Peer Count', String(health.peer_count != null ? health.peer_count : assignedPeers.length)],
      ['Cloak Public Key', service.cloak_public_key || '-'],
      ['Last Error', service.last_error_text || '-']
    ])
    + '<div class="stitle">Assigned Peers</div>'
    + '<div style="margin-top:8px;">' + peerRows + '</div>'
    + '<div class="dp-actions">'
      +'<button class="btn" onclick="actionOpenvpnCloakAssignPeer(\''+esc(service.id)+'\')">ASSIGN PEER</button>'
      +'<button class="btn pri" onclick="actionOpenvpnCloakApply(\''+esc(service.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openOpenvpnCloakServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteOpenvpnCloakServiceFlow(\''+esc(service.id)+'\')">DELETE</button>'
    +'</div>'
  );
};

window.openOpenvpnCloakServiceModal = function openOpenvpnCloakServiceModal(serviceId){
  var service = serviceId ? openvpnCloakServiceById(serviceId) : null;
  var nodeOptions = NODES.map(function(node){ return {value:node.id, label:node.name}; });
  var body = '<form id="openvpnCloakServiceForm"><div class="modal-grid">'
    +formInput('Name', 'name', service ? service.name : '', {required:true})
    +formSelect('Node', 'node_id', service ? service.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions, {help:'Managed node where OpenVPN+Cloak will run.'})
    +formInput('OpenVPN local host', 'openvpn_local_host', service ? service.openvpn_local_host : '127.0.0.1', {required:true})
    +formInput('OpenVPN local port', 'openvpn_local_port', service ? String(service.openvpn_local_port) : '11940', {type:'number', required:true})
    +formInput('Cloak listen host', 'cloak_listen_host', service ? service.cloak_listen_host : '0.0.0.0', {required:true})
    +formInput('Cloak listen port', 'cloak_listen_port', service ? String(service.cloak_listen_port) : '443', {type:'number', required:true})
    +formInput('Public host', 'public_host', service ? service.public_host : '', {required:true})
    +formInput('Public port', 'public_port', service && service.public_port != null ? String(service.public_port) : '', {type:'number'})
    +formInput('Server name', 'server_name', service ? (service.server_name || '') : '')
    +formInput('Client local port', 'client_local_port', service ? String(service.client_local_port) : '28947', {type:'number', required:true})
    +formInput('Server network', 'server_network_v4', service ? service.server_network_v4 : '10.251.0.0/24', {required:true})
    +formInput('DNS server', 'dns_server_v4', service ? (service.dns_server_v4 || '') : '')
    +formInput('MTU', 'mtu', service ? String(service.mtu) : '1500', {type:'number'})
    +formTextarea('Client allowed IPs', 'client_allowed_ips_json', service ? (service.client_allowed_ips_json || []).join(', ') : '0.0.0.0/0, ::/0', {help:'Comma-separated CIDRs.'})
    +'</div></form>';
  openModal(service ? 'Edit service' : 'Create service', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:service ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('openvpnCloakServiceForm').requestSubmit(); }}
    ]
  });
  bindNodeHostAutofill('openvpnCloakServiceForm', 'node_id', 'public_host');
  bindModalForm('openvpnCloakServiceForm', function(fd){ saveOpenvpnCloakServiceForm(fd, serviceId); });
};

window.deleteOpenvpnCloakServiceFlow = async function deleteOpenvpnCloakServiceFlow(serviceId){
  var service = openvpnCloakServiceById(serviceId);
  if(!confirm('Delete OpenVPN+Cloak service ' + (service ? service.name : serviceId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/openvpn-cloak-services/' + encodeURIComponent(serviceId), { method:'DELETE' });
    pushEv('openvpn_cloak_service.deleted', 'OpenVPN+Cloak service deleted: ' + (service ? service.name : serviceId));
    await refreshOpenvpnCloakServices();
    closeDP();
  }catch(err){
    pushEv('openvpn_cloak_service.error', 'delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionOpenvpnCloakApply = async function actionOpenvpnCloakApply(serviceId){
  try{
    var service = openvpnCloakServiceById(serviceId);
    var applied = await apiFetch(API_PREFIX + '/openvpn-cloak-services/' + encodeURIComponent(serviceId) + '/apply', { method:'POST', body:{} });
    pushEv('openvpn_cloak_service.applied', 'OpenVPN+Cloak service applied: ' + ((applied && applied.name) || (service && service.name) || serviceId));
    await Promise.all([refreshOpenvpnCloakServices(), loadPeers()]);
    if(service){ window.showOpenvpnCloakService(serviceId); }
  }catch(err){
    pushEv('openvpn_cloak_service.error', 'apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionOpenvpnCloakAssignPeer = async function actionOpenvpnCloakAssignPeer(serviceId){
  var service = openvpnCloakServiceById(serviceId);
  if(!service) return;
  if(!PEERS.length){ await loadPeers(); }
  var peerOptions = PEERS.filter(function(peer){ return peer.is_active !== false && !peer.revoked_at; }).map(function(peer){
    return {value: peer.id, label: (peer.username || peer.email || peer.id) + ' — ' + (peer.email || 'no-email')};
  });
  if(!peerOptions.length){ alert('No active peers available.'); return; }
  var body = '<form id="openvpnCloakAssignPeerForm"><div class="modal-grid">'
    +formSelect('Peer', 'peer_id', peerOptions[0].value, peerOptions, {full:true})
    +formCheckbox('Save config to peer', 'save_to_peer', true, {caption:'Persist generated client config to peer record', full:true})
    +'</div></form>';
  openModal('Assign Peer — ' + service.name, body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Assign', className:'btn pri', onClick:function(){ document.getElementById('openvpnCloakAssignPeerForm').requestSubmit(); }}
    ]
  });
  bindModalForm('openvpnCloakAssignPeerForm', function(fd){ submitOpenvpnCloakAssignPeer(serviceId, fd); });
};

export {};
