// Page module - all functions exposed as window globals

window.renderLinks = function renderLinks(){
  var filters = getLinkFilters();
  var rowsData = LINKS.filter(function(l){
    var haystack = [
      l.name,
      l.driver,
      nById(l.left).name,
      nById(l.right).name,
      l.topo,
      l.state,
      l.leftInterface,
      l.rightInterface,
      l.leftEndpoint,
      l.rightEndpoint
    ].join(' ').toLowerCase();
    if(filters.search && haystack.indexOf(filters.search) === -1){ return false; }
    if(filters.state && String(l.state || '').toLowerCase() !== filters.state){ return false; }
    return true;
  });
  document.getElementById('ltb').innerHTML = rowsData.length ? rowsData.map(function(l){
    return '<tr onclick="showLink(\''+esc(l.id)+'\')">'
      +'<td class="m">'+esc(l.name)+'</td>'
      +'<td><span class="pill pb">'+esc(l.driver)+'</span></td>'
      +'<td class="m">'+esc(nById(l.left).name)+'</td>'
      +'<td class="m">'+esc(nById(l.right).name)+'</td>'
      +'<td><span class="pill pp">'+esc(l.topo)+'</span></td>'
      +'<td>'+sp(l.state)+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionLinkValidate(\''+esc(l.id)+'\')">VALIDATE</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();actionLinkApply(\''+esc(l.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openLinkModal(\''+esc(l.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteLinkFlow(\''+esc(l.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('') : '<tr><td class="empty-state" colspan="7">No links match the current filter.</td></tr>';
};

window.showLink = function showLink(id){
  var l = linkById(id); if(!l) return;
  openDP(l.name,
    rows([
      ['ID',l.id],
      ['Driver',l.driver],
      ['Left Node',nById(l.left).name],
      ['Right Node',nById(l.right).name],
      ['Topology',l.topo],
      ['State',l.state],
      ['Left Iface',l.leftInterface || '-'],
      ['Right Iface',l.rightInterface || '-'],
      ['Left Endpoint',l.leftEndpoint || '-'],
      ['Right Endpoint',l.rightEndpoint || '-']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="actionLinkValidate(\''+esc(l.id)+'\')">VALIDATE</button>'
      +'<button class="btn pri" onclick="actionLinkApply(\''+esc(l.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openLinkModal(\''+esc(l.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteLinkFlow(\''+esc(l.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'link', id:l.id }
  );
};

window.refreshLinks = async function refreshLinks(){
  var links = await apiFetch(API_PREFIX + '/links');
  LINKS = (links || []).map(function(link){
    var spec = link.desired_spec_json || {};
    return {
      id: link.id,
      name: link.name,
      driver: link.driver_name,
      left: link.left_node_id,
      right: link.right_node_id,
      topo: link.topology_type,
      state: link.state,
      spec: spec,
      leftInterface: spec.left && spec.left.interface_name,
      rightInterface: spec.right && spec.right.interface_name,
      leftEndpoint: spec.left && spec.left.endpoint_host ? (spec.left.endpoint_host + ':' + (spec.left.listen_port || '')) : '',
      rightEndpoint: spec.right && spec.right.endpoint_host ? (spec.right.endpoint_host + ':' + (spec.right.listen_port || '')) : ''
    };
  });
  renderLinks();
};

window.openLinkModal = function openLinkModal(linkId){
  var link = linkId ? linkById(linkId) : null;
  var spec = link && link.spec ? link.spec : {};
  var left = spec.left || {};
  var right = spec.right || {};
  var peer = spec.peer || {};
  var obf = spec.awg_obfuscation || {};
  var obfDefaults = awgDefaultObfuscation();
  var nodeOptions = NODES.map(function(n){ return {value:n.id, label:n.name}; });
  var body = '<form id="linkForm"><div class="modal-grid">'
    +formInput('Link name', 'name', link ? link.name : '', {required:true})
    +formSelect('Topology', 'topology_type', link ? link.topo : 'p2p', ['p2p','upstream','relay','balancer_member','service_edge'])
    +formSelect('Left node', 'left_node_id', link ? link.left : '', nodeOptions)
    +formSelect('Right node', 'right_node_id', link ? link.right : '', nodeOptions)
    +formInput('Left interface', 'left_interface_name', left.interface_name || 'awg10', {required:true})
    +formInput('Right interface', 'right_interface_name', right.interface_name || 'awg11', {required:true})
    +formInput('Left port', 'left_listen_port', left.listen_port || '8443', {required:true, type:'number'})
    +formInput('Right port', 'right_listen_port', right.listen_port || '8444', {required:true, type:'number'})
    +formInput('Left IPv4/CIDR', 'left_address_v4', left.address_v4 || '10.77.77.1/30', {required:true})
    +formInput('Right IPv4/CIDR', 'right_address_v4', right.address_v4 || '10.77.77.2/30', {required:true})
    +formInput('Left endpoint host', 'left_endpoint_host', left.endpoint_host || '', {required:true})
    +formInput('Right endpoint host', 'right_endpoint_host', right.endpoint_host || '', {required:true})
    +formInput('Left MTU', 'left_mtu', left.mtu || '1420', {required:true, type:'number'})
    +formInput('Right MTU', 'right_mtu', right.mtu || '1420', {required:true, type:'number'})
    +formInput('Peer keepalive', 'persistent_keepalive', peer.persistent_keepalive || '21', {required:true, type:'number'})
    +formInput('Peer MTU', 'peer_mtu', peer.mtu || '1420', {required:true, type:'number'})
    +formTextarea('Left allowed IPs (CSV)', 'left_allowed_ips', (peer.left_allowed_ips || ['10.77.77.2/32']).join(','), {full:false})
    +formTextarea('Right allowed IPs (CSV)', 'right_allowed_ips', (peer.right_allowed_ips || ['10.77.77.1/32']).join(','), {full:false})
    +formInput('Jc', 'jc', obfValue(obf, 'jc', obfDefaults.jc), {type:'number'})
    +formInput('Jmin', 'jmin', obfValue(obf, 'jmin', obfDefaults.jmin), {type:'number'})
    +formInput('Jmax', 'jmax', obfValue(obf, 'jmax', obfDefaults.jmax), {type:'number'})
    +formInput('S1', 's1', obfValue(obf, 's1', obfDefaults.s1), {type:'number'})
    +formInput('S2', 's2', obfValue(obf, 's2', obfDefaults.s2), {type:'number'})
    +formInput('S3', 's3', obfValue(obf, 's3', obfDefaults.s3), {type:'number'})
    +formInput('S4', 's4', obfValue(obf, 's4', obfDefaults.s4), {type:'number'})
    +formInput('H1', 'h1', obfValue(obf, 'h1', obfDefaults.h1), {type:'number'})
    +formInput('H2', 'h2', obfValue(obf, 'h2', obfDefaults.h2), {type:'number'})
    +formInput('H3', 'h3', obfValue(obf, 'h3', obfDefaults.h3), {type:'number'})
    +formInput('H4', 'h4', obfValue(obf, 'h4', obfDefaults.h4), {type:'number'})
    +'</div></form>';
  openModal(link ? 'Edit Link' : 'Create Link', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: link ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('linkForm').requestSubmit(); }}
    ]
  });
  bindModalForm('linkForm', function(fd){ saveLinkForm(fd, linkId); });
  var form = document.getElementById('linkForm');
  if(!form) return;
  var leftNodeSelect = form.querySelector('[name="left_node_id"]');
  var rightNodeSelect = form.querySelector('[name="right_node_id"]');
  var leftEndpointInput = form.querySelector('[name="left_endpoint_host"]');
  var rightEndpointInput = form.querySelector('[name="right_endpoint_host"]');

  function nodeMgmtHost(nodeId){
    var node = nById(String(nodeId || '').trim());
    return node ? String(node.management_address || node.ssh_host || '').trim() : '';
  }

  function syncEndpointDefault(input, nodeId){
    if(!input) return;
    var current = String(input.value || '').trim();
    var fallback = nodeMgmtHost(nodeId);
    var initial = String(input.getAttribute('data-initial-value') || '').trim();
    var dirty = input.getAttribute('data-dirty') === '1';
    if(!dirty || current === '' || current === initial){
      input.value = fallback;
      input.setAttribute('data-initial-value', fallback);
      input.setAttribute('data-dirty', '0');
    }
  }

  [leftEndpointInput, rightEndpointInput].forEach(function(input){
    if(!input) return;
    input.setAttribute('data-initial-value', String(input.value || '').trim());
    input.setAttribute('data-dirty', '0');
    input.addEventListener('input', function(){
      var current = String(input.value || '').trim();
      var initial = String(input.getAttribute('data-initial-value') || '').trim();
      input.setAttribute('data-dirty', current !== initial ? '1' : '0');
    });
  });

  if(leftNodeSelect){
    leftNodeSelect.addEventListener('change', function(){
      syncEndpointDefault(leftEndpointInput, leftNodeSelect.value);
    });
    syncEndpointDefault(leftEndpointInput, leftNodeSelect.value);
  }
  if(rightNodeSelect){
    rightNodeSelect.addEventListener('change', function(){
      syncEndpointDefault(rightEndpointInput, rightNodeSelect.value);
    });
    syncEndpointDefault(rightEndpointInput, rightNodeSelect.value);
  }
};

window.deleteLinkFlow = async function deleteLinkFlow(linkId){
  var link = linkById(linkId);
  if(!confirm('Delete link ' + (link ? link.name : linkId) + '?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/links/' + encodeURIComponent(linkId), { method:'DELETE' });
    pushEv('link.deleted', 'link ' + (link ? link.name : linkId) + ' deleted');
    closeDP();
    await refreshLinks();
  }catch(err){
    pushEv('link.delete.error', 'delete failed for ' + linkId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionLinkValidate = async function actionLinkValidate(linkId){
  try{
    var link = linkById(linkId);
    var result = await apiFetch(API_PREFIX + '/links/' + encodeURIComponent(linkId) + '/validate', { method:'POST', body:{} });
    var warnings = (result.warnings || []).length ? (' warnings: ' + result.warnings.join('; ')) : '';
    pushEv(result.valid ? 'link.validate.ok' : 'link.validate.fail', 'validate ' + (link ? link.name : linkId) + ': ' + (result.valid ? 'valid' : 'invalid') + warnings);
    await refreshLinks();
    await refreshTopology();
    if(link && document.getElementById('dp').classList.contains('open') && detailContextIs('link', linkId)){ showLink(linkId); }
  }catch(err){
    pushEv('link.validate.error', 'validate failed for ' + linkId + ': ' + (err && err.message ? err.message : err));
  }
};

window.actionLinkApply = async function actionLinkApply(linkId){
  try{
    var link = linkById(linkId);
    var job = await apiFetch(API_PREFIX + '/links/' + encodeURIComponent(linkId) + '/apply', { method:'POST', body:{} });
    pushEv('job.created', 'apply queued for ' + (link ? link.name : linkId) + ' [' + job.id + ']');
    await refreshJobs();
    setTimeout(function(){ refreshLinks().catch(function(){}); refreshJobs().catch(function(){}); refreshTopology().catch(function(){}); }, 800);
    if(link && document.getElementById('dp').classList.contains('open') && detailContextIs('link', linkId)){ showLink(linkId); }
  }catch(err){
    pushEv('link.apply.error', 'apply failed for ' + linkId + ': ' + (err && err.message ? err.message : err));
  }
};

window.saveLinkForm = async function saveLinkForm(fd, linkId){
  function csv(v){ return String(v||'').split(',').map(function(x){return x.trim();}).filter(Boolean); }
  function num(v){ return parseInt(v, 10) || 0; }
  var spec = {
    mode: 'site_to_site',
    left: {
      interface_name: fd.get('left_interface_name'),
      listen_port: num(fd.get('left_listen_port')),
      address_v4: fd.get('left_address_v4'),
      mtu: num(fd.get('left_mtu')),
      endpoint_host: fd.get('left_endpoint_host')
    },
    right: {
      interface_name: fd.get('right_interface_name'),
      listen_port: num(fd.get('right_listen_port')),
      address_v4: fd.get('right_address_v4'),
      mtu: num(fd.get('right_mtu')),
      endpoint_host: fd.get('right_endpoint_host')
    },
    peer: {
      persistent_keepalive: num(fd.get('persistent_keepalive')),
      mtu: num(fd.get('peer_mtu')),
      left_allowed_ips: csv(fd.get('left_allowed_ips')),
      right_allowed_ips: csv(fd.get('right_allowed_ips'))
    },
    awg_obfuscation: {
      jc:   num(fd.get('jc')),
      jmin: num(fd.get('jmin')),
      jmax: num(fd.get('jmax')),
      s1:   num(fd.get('s1')),
      s2:   num(fd.get('s2')),
      s3:   num(fd.get('s3')),
      s4:   num(fd.get('s4')),
      h1:   num(fd.get('h1')),
      h2:   num(fd.get('h2')),
      h3:   num(fd.get('h3')),
      h4:   num(fd.get('h4'))
    }
  };
  var payload;
  if(linkId){
    payload = {
      name: fd.get('name'),
      topology_type: fd.get('topology_type'),
      left_node_id: fd.get('left_node_id'),
      right_node_id: fd.get('right_node_id'),
      spec: spec
    };
  }else{
    payload = {
      name: fd.get('name'),
      driver_name: 'awg',
      topology_type: fd.get('topology_type'),
      left_node_id: fd.get('left_node_id'),
      right_node_id: fd.get('right_node_id'),
      spec: spec
    };
  }
  try{
    if(linkId){
      await apiFetch(API_PREFIX+'/links/'+encodeURIComponent(linkId), {method:'PATCH', body:payload});
    }else{
      await apiFetch(API_PREFIX+'/links', {method:'POST', body:payload});
    }
    closeModal();
    await refreshLinks();
    await refreshTopology();
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

export {};
