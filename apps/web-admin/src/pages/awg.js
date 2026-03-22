// Page module - all functions exposed as window globals

window.refreshAwgServices = async function refreshAwgServices(){
  try{
    var data = await apiFetch(API_PREFIX + '/awg-services');
    AWG_SERVICES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!AWG_SERVICES.length) AWG_SERVICES = [];
  }
  window.renderAwgServices();
};

window.renderAwgServices = function renderAwgServices(){
  var tb = document.getElementById('awgtb');
  if(!tb) return;
  if(!AWG_SERVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="8">No AWG services.</td></tr>';
    return;
  }
  tb.innerHTML = AWG_SERVICES.map(function(service){
    var publicEndpoint = service.public_host + ':' + String(service.public_port || service.listen_port);
    return '<tr onclick="showAwgService(\''+esc(service.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(service.name)+'</td>'
      +'<td>'+esc(nById(service.node_id).name)+'</td>'
      +'<td class="m">'+esc(service.interface_name)+'</td>'
      +'<td class="m">'+esc(publicEndpoint)+'</td>'
      +'<td class="m">'+esc(service.server_address_v4 || '-')+'</td>'
      +'<td>'+esc(String(awgPeerCount(service.id)))+'</td>'
      +'<td>'+sp(service.state)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionAwgAssignPeer(\''+esc(service.id)+'\')">ASSIGN</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionAwgApply(\''+esc(service.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openAwgServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteAwgServiceFlow(\''+esc(service.id)+'\')">DEL</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.showAwgService = function showAwgService(id){
  var service = awgServiceById(id);
  if(!service) return;
  var assignedPeers = PEERS.filter(function(peer){ return peer.awg_service_id === service.id && peer.is_active !== false && !peer.revoked_at; });
  var peerRows = assignedPeers.length ? assignedPeers.map(function(peer){
    return '<div class="drow"><span class="dk">'+esc(peer.username || peer.email || peer.id)+'</span><span class="dv">'+esc((peer.awg_address_v4 || '-') + ' / ' + (peer.email || '-'))+'</span></div>';
  }).join('') : '<div class="drow"><span class="dk">No peers</span><span class="dv">-</span></div>';
  var health = service.health_summary_json || {};
  openDP('AWG ' + service.name,
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
      +'<button class="btn" onclick="actionAwgAssignPeer(\''+esc(service.id)+'\')">ASSIGN PEER</button>'
      +'<button class="btn pri" onclick="actionAwgApply(\''+esc(service.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openAwgServiceModal(\''+esc(service.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteAwgServiceFlow(\''+esc(service.id)+'\')">DELETE</button>'
    +'</div>'
  );
};

window.openAwgServiceModal = function openAwgServiceModal(serviceId){
  var service = serviceId ? awgServiceById(serviceId) : null;
  var nodeOptions = NODES.map(function(node){ return {value:node.id, label:node.name}; });
  var obf = service && service.awg_obfuscation_json ? service.awg_obfuscation_json : awgDefaultObfuscation();
  var obfDefaults = awgDefaultObfuscation();
  var body = '<form id="awgServiceForm"><div class="modal-grid">'
    +formInput('Name', 'name', service ? service.name : '', {required:true})
    +formSelect('Node', 'node_id', service ? service.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions, {help:'Managed node where AWG will run.'})
    +formInput('Interface', 'interface_name', service ? service.interface_name : 'awg0', {required:true})
    +formInput('Listen port', 'listen_port', service ? String(service.listen_port) : '51820', {type:'number', required:true})
    +formInput('Public host', 'public_host', service ? service.public_host : '', {required:true})
    +formInput('Public port', 'public_port', service && service.public_port != null ? String(service.public_port) : '', {type:'number'})
    +formInput('Server address', 'server_address_v4', service ? service.server_address_v4 : '10.250.0.1/24', {required:true})
    +formInput('DNS server', 'dns_server_v4', service ? (service.dns_server_v4 || '') : '')
    +formInput('MTU', 'mtu', service ? String(service.mtu) : '1420', {type:'number'})
    +formInput('Keepalive', 'persistent_keepalive', service ? String(service.persistent_keepalive) : '25', {type:'number'})
    +formTextarea('Client allowed IPs', 'client_allowed_ips_json', service ? (service.client_allowed_ips_json || []).join(', ') : '0.0.0.0/0, ::/0', {help:'Comma-separated CIDRs.'})
    +formInput('Jc', 'jc', obfValue(obf, 'jc', obfDefaults.jc), {type:'number', help:'Range: 1..128'})
    +formInput('Jmin', 'jmin', obfValue(obf, 'jmin', obfDefaults.jmin), {type:'number', help:'Range: 0..Jmax-1'})
    +formInput('Jmax', 'jmax', obfValue(obf, 'jmax', obfDefaults.jmax), {type:'number', help:'Range: Jmin+1..MTU'})
    +formInput('S1', 's1', obfValue(obf, 's1', obfDefaults.s1), {type:'number', help:'Range: 0..MTU-148'})
    +formInput('S2', 's2', obfValue(obf, 's2', obfDefaults.s2), {type:'number', help:'Range: 0..MTU-92; S1+56 must not equal S2'})
    +formInput('S3', 's3', obfValue(obf, 's3', obfDefaults.s3), {type:'number', help:'Range: 0..MTU'})
    +formInput('S4', 's4', obfValue(obf, 's4', obfDefaults.s4), {type:'number', help:'Range: 0..MTU'})
    +formInput('H1', 'h1', obfValue(obf, 'h1', obfDefaults.h1), {type:'number', help:'Range: 0..4294967295; unique'})
    +formInput('H2', 'h2', obfValue(obf, 'h2', obfDefaults.h2), {type:'number', help:'Range: 0..4294967295; unique'})
    +formInput('H3', 'h3', obfValue(obf, 'h3', obfDefaults.h3), {type:'number', help:'Range: 0..4294967295; unique'})
    +formInput('H4', 'h4', obfValue(obf, 'h4', obfDefaults.h4), {type:'number', help:'Range: 0..4294967295; unique'})
    +'</div></form>';
  openModal(service ? 'Edit service' : 'Create service', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:service ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('awgServiceForm').requestSubmit(); }}
    ]
  });
  bindNodeHostAutofill('awgServiceForm', 'node_id', 'public_host');
  bindModalForm('awgServiceForm', function(fd){ saveAwgServiceForm(fd, serviceId); });
};

window.deleteAwgServiceFlow = async function deleteAwgServiceFlow(serviceId){
  var service = awgServiceById(serviceId);
  if(!confirm('Delete AWG service ' + (service ? service.name : serviceId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/awg-services/' + encodeURIComponent(serviceId), { method:'DELETE' });
    pushEv('awg_service.deleted', 'AWG service deleted: ' + (service ? service.name : serviceId));
    await refreshAwgServices();
    closeDP();
  }catch(err){
    pushEv('awg_service.error', 'delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionAwgApply = async function actionAwgApply(serviceId){
  try{
    var service = awgServiceById(serviceId);
    var applied = await apiFetch(API_PREFIX + '/awg-services/' + encodeURIComponent(serviceId) + '/apply', { method:'POST', body:{} });
    pushEv('awg_service.applied', 'AWG service applied: ' + ((applied && applied.name) || (service && service.name) || serviceId));
    await Promise.all([refreshAwgServices(), loadPeers()]);
    if(service){ window.showAwgService(serviceId); }
  }catch(err){
    pushEv('awg_service.error', 'apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionAwgAssignPeer = async function actionAwgAssignPeer(serviceId){
  var service = awgServiceById(serviceId);
  if(!service) return;
  if(!PEERS.length){ await loadPeers(); }
  var peerOptions = PEERS.filter(function(peer){ return peer.is_active !== false && !peer.revoked_at; }).map(function(peer){
    return {value: peer.id, label: (peer.username || peer.email || peer.id) + ' — ' + (peer.email || 'no-email')};
  });
  if(!peerOptions.length){ alert('No active peers available.'); return; }
  var body = '<form id="awgAssignPeerForm"><div class="modal-grid">'
    +formSelect('Peer', 'peer_id', peerOptions[0].value, peerOptions, {full:true})
    +formCheckbox('Save config to peer', 'save_to_peer', true, {caption:'Persist generated client config to peer record', full:true})
    +'</div></form>';
  openModal('Assign Peer — ' + service.name, body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Assign', className:'btn pri', onClick:function(){ document.getElementById('awgAssignPeerForm').requestSubmit(); }}
    ]
  });
  bindModalForm('awgAssignPeerForm', function(fd){ submitAwgAssignPeer(serviceId, fd); });
};

export {};
