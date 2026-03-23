// Page module - all functions exposed as window globals

window.renderPolicies = function renderPolicies(){
  document.getElementById('ptb').innerHTML = POLICIES.map(function(p){
    return '<tr onclick="showRoutePolicy(\''+esc(p.id)+'\')">'
      +'<td class="m">'+esc(p.name)+'</td>'
      +'<td class="m">'+esc(nById(p.nid).name)+'</td>'
      +'<td><span class="pill pb">'+esc(p.action)+'</span></td>'
      +'<td>'+esc(String(p.pri))+'</td>'
      +'<td>'+(p.on?'<span class="pill pg">enabled</span>':'<span class="pill pq">disabled</span>')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionRoutePolicyApply(\''+esc(p.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();actionRoutePolicyTest(\''+esc(p.id)+'\')">SAFE TEST 2M</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openRoutePolicyModal(\''+esc(p.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteRoutePolicyFlow(\''+esc(p.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
  document.getElementById('dtb').innerHTML = DNS_P.map(function(d){
    return '<tr onclick="showDNSPolicy(\''+esc(d.id)+'\')">'
      +'<td class="m">'+esc(policyNameById(d.route_policy_id))+'</td>'
      +'<td class="m">'+esc(d.addr)+'</td>'
      +'<td>'+(d.on?'<span class="pill pg">enabled</span>':'<span class="pill pq">disabled</span>')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionDNSPolicyApply(\''+esc(d.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openDNSPolicyModal(\''+esc(d.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteDNSPolicyFlow(\''+esc(d.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
  document.getElementById('gtb').innerHTML = (GEO_P.length ? GEO_P.map(function(g){
    return '<tr onclick="showGeoPolicy(\''+esc(g.id)+'\')">'
      +'<td class="m">'+esc(policyNameById(g.route_policy_id))+'</td>'
      +'<td class="m">'+esc(g.country_code)+'</td>'
      +'<td><span class="pill pp">'+esc(g.mode)+'</span></td>'
      +'<td>'+(g.enabled?'<span class="pill pg">enabled</span>':'<span class="pill pq">disabled</span>')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionGeoPolicyApply(\''+esc(g.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openGeoPolicyModal(\''+esc(g.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteGeoPolicyFlow(\''+esc(g.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('') : '<tr><td class="empty-state" colspan="5">No geo policies.</td></tr>');
  document.getElementById('btb').innerHTML = (BALANCERS.length ? BALANCERS.map(function(b){
    return '<tr onclick="showBalancer(\''+esc(b.id)+'\')">'
      +'<td class="m">'+esc(b.name)+'</td>'
      +'<td class="m">'+esc(nById(b.node_id).name)+'</td>'
      +'<td><span class="pill pb">'+esc(b.method)+'</span></td>'
      +'<td>'+esc(String((b.members || []).length))+'</td>'
      +'<td>'+(b.enabled?'<span class="pill pg">enabled</span>':'<span class="pill pq">disabled</span>')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionBalancerPick(\''+esc(b.id)+'\')">PICK</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openBalancerModal(\''+esc(b.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteBalancerFlow(\''+esc(b.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('') : '<tr><td class="empty-state" colspan="6">No balancers.</td></tr>');
  renderPolicyTransitHub();
};

window.showRoutePolicy = function showRoutePolicy(id){
  var p = policyById(id); if(!p) return;
  openDP(p.name,
    rows([
      ['ID', p.id],
      ['Node', nById(p.nid).name],
      ['Action', p.action],
      ['Ingress', p.ingress_interface || '-'],
      ['Target Interface', p.target_interface || '-'],
      ['Target Gateway', p.target_gateway || '-'],
      ['Balancer', (balancerById(p.balancer_id) || {}).name || p.balancer_id || '-'],
      ['Routed Networks', (p.routed_networks || []).join(', ') || '-'],
      ['Excluded Networks', (p.excluded_networks || []).join(', ') || '-'],
      ['Table ID', p.table_id || '-'],
      ['Priority', p.pri || '-'],
      ['Firewall Mark', p.fwmark || '-'],
      ['Masquerade', p.masquerade ? 'yes' : 'no'],
      ['State', p.on ? 'enabled' : 'disabled']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="actionRoutePolicyApply(\''+esc(p.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="actionRoutePolicyTest(\''+esc(p.id)+'\')">SAFE TEST 2M</button>'
      +'<button class="btn" onclick="openRoutePolicyModal(\''+esc(p.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteRoutePolicyFlow(\''+esc(p.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'route-policy', id:p.id }
  );
};

window.showDNSPolicy = function showDNSPolicy(id){
  var p = dnsPolicyById(id); if(!p) return;
  openDP('DNS Policy',
    rows([
      ['ID', p.id],
      ['Route Policy', policyNameById(p.route_policy_id)],
      ['DNS Address', p.addr || '-'],
      ['Capture Protocols', (p.capture_protocols || []).join(', ') || '-'],
      ['Capture Ports', (p.capture_ports || []).join(', ') || '-'],
      ['Exceptions', (p.exceptions_networks || []).join(', ') || '-'],
      ['State', p.on ? 'enabled' : 'disabled']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="actionDNSPolicyApply(\''+esc(p.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openDNSPolicyModal(\''+esc(p.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteDNSPolicyFlow(\''+esc(p.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'dns-policy', id:p.id }
  );
};

window.showGeoPolicy = function showGeoPolicy(id){
  var p = geoPolicyById(id); if(!p) return;
  openDP('Geo Policy',
    rows([
      ['ID', p.id],
      ['Route Policy', policyNameById(p.route_policy_id)],
      ['Country', p.country_code || '-'],
      ['Mode', p.mode || '-'],
      ['Source URL', p.source_url_template || '-'],
      ['State', p.enabled ? 'enabled' : 'disabled']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="actionGeoPolicyApply(\''+esc(p.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openGeoPolicyModal(\''+esc(p.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteGeoPolicyFlow(\''+esc(p.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'geo-policy', id:p.id }
  );
};

window.showBalancer = function showBalancer(id){
  var b = balancerById(id); if(!b) return;
  var members = (b.members || []).map(function(member){
    return [
      member.interface_name || '-',
      member.gateway || '-',
      member.ping_target || '-',
      member.weight || 1
    ].join(' / ');
  }).join('\n');
  openDP(b.name,
    rows([
      ['ID', b.id],
      ['Node', nById(b.node_id).name],
      ['Method', b.method || '-'],
      ['Members', String((b.members || []).length)],
      ['Enabled', b.enabled ? 'yes' : 'no']
    ])
    +'<div class="stitle">Members</div>'
    +'<div class="jlog">'+esc(members || 'No members defined.')+'</div>'
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="actionBalancerPick(\''+esc(b.id)+'\')">PICK</button>'
      +'<button class="btn" onclick="openBalancerModal(\''+esc(b.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteBalancerFlow(\''+esc(b.id)+'\')">DELETE</button>'
    +'</div>',
    { kind:'balancer', id:b.id }
  );
};

window.refreshPolicies = async function refreshPolicies(){
  var routePolicies = await apiFetch(API_PREFIX + '/route-policies');
  var dnsPolicies = await apiFetch(API_PREFIX + '/dns-policies');
  var geoPolicies = await apiFetch(API_PREFIX + '/geo-policies');
  var balancers = await apiFetch(API_PREFIX + '/balancers');
  POLICIES = (routePolicies || []).map(function(policy){
    return {
      id: policy.id,
      nid: policy.node_id,
      name: policy.name,
      action: policy.action,
      ingress_interface: policy.ingress_interface,
      target_interface: policy.target_interface,
      target_gateway: policy.target_gateway,
      balancer_id: policy.balancer_id,
      routed_networks: policy.routed_networks || [],
      excluded_networks: policy.excluded_networks || [],
      table_id: policy.table_id,
      pri: policy.rule_priority,
      fwmark: policy.firewall_mark,
      masquerade: !!policy.masquerade,
      on: !!policy.enabled
    };
  });
  DNS_P = (dnsPolicies || []).map(function(policy){
    return {
      id: policy.id,
      route_policy_id: policy.route_policy_id,
      addr: policy.dns_address,
      capture_protocols: policy.capture_protocols || [],
      capture_ports: policy.capture_ports || [],
      exceptions_networks: policy.exceptions_networks || [],
      on: !!policy.enabled
    };
  });
  GEO_P = (geoPolicies || []).map(function(policy){
    return {
      id: policy.id,
      route_policy_id: policy.route_policy_id,
      country_code: policy.country_code,
      mode: policy.mode,
      source_url_template: policy.source_url_template,
      enabled: !!policy.enabled
    };
  });
  BALANCERS = balancers || [];
  renderPolicies();
};

window.openRoutePolicyModal = function openRoutePolicyModal(policyId){
  var policy = policyId ? policyById(policyId) : null;
  var nodeOptions = NODES.map(function(n){ return {value:n.id, label:n.name}; });
  var balancerOptions = [{value:'', label:'-'}].concat(BALANCERS.map(function(b){ return {value:b.id, label:b.name}; }));
  var initialNodeId = policy ? policy.nid : (NODES[0] ? NODES[0].id : '');
  var initialIngress = routePolicyDefaultIngress(initialNodeId, policy ? policy.ingress_interface : '');
  var initialTarget = routePolicyDefaultTarget(initialNodeId, initialIngress, policy ? (policy.target_interface || '') : '');
  var initialGateway = routePolicyDefaultGateway(initialNodeId, initialTarget, policy ? (policy.target_gateway || '') : '');
  var body = '<form id="routePolicyForm"><div class="modal-grid">'
    +formSelect('Node', 'node_id', initialNodeId, nodeOptions)
    +formInput('Policy name', 'name', policy ? policy.name : '', {required:true})
    +formSelect('Ingress interface', 'ingress_interface', initialIngress, routePolicyInterfaceOptions(initialNodeId, initialIngress), {help:'Interfaces come from the latest Probe SSH snapshot.'})
    +formSelect('Action', 'action', policy ? policy.action : 'next_hop', ['direct','next_hop','balancer'])
    +formSelect('Target interface', 'target_interface', initialTarget, routePolicyInterfaceOptions(initialNodeId, initialTarget), {help:'Control-plane SSH access is preserved automatically.'})
    +formInput('Target gateway', 'target_gateway', initialGateway, {help:'Autofilled from the latest Probe SSH default route for the selected target interface.'})
    +formSelect('Balancer', 'balancer_id', policy ? (policy.balancer_id || '') : '', balancerOptions)
    +formInput('Table ID', 'table_id', policy ? policy.table_id : '51820', {type:'number'})
    +formInput('Rule priority', 'rule_priority', policy ? policy.pri : '10000', {type:'number'})
    +formInput('Firewall mark', 'firewall_mark', policy ? policy.fwmark : '51820', {type:'number'})
    +formCheckbox('Masquerade', 'masquerade', policy ? policy.masquerade : true, {caption:'Enable masquerade'})
    +formCheckbox('Enabled', 'enabled', policy ? policy.on : true, {caption:'Policy enabled'})
    +formTextarea('Routed networks (CSV)', 'routed_networks', policy ? (policy.routed_networks || []).join(',') : '0.0.0.0/0', {full:true})
    +formTextarea('Excluded networks (CSV)', 'excluded_networks', policy ? (policy.excluded_networks || []).join(',') : '', {full:true})
    +'</div></form>';
  openModal(policy ? 'Edit Route Policy' : 'Create Route Policy', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      policy ? {label:'Safe test 2m', className:'btn', onClick:function(){ actionRoutePolicyTest(policy.id); }} : null,
      {label: policy ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('routePolicyForm').requestSubmit(); }}
    ].filter(Boolean)
  });
  var nodeEl = document.getElementById('node_id');
  var ingressEl = document.getElementById('ingress_interface');
  var targetEl = document.getElementById('target_interface');
  var gatewayEl = document.getElementById('target_gateway');
  if(nodeEl){ nodeEl.addEventListener('change', syncRoutePolicyInterfaceSelectors); }
  if(ingressEl){ ingressEl.addEventListener('change', syncRoutePolicyInterfaceSelectors); }
  if(targetEl){ targetEl.addEventListener('change', syncRoutePolicyInterfaceSelectors); }
  if(gatewayEl){
    gatewayEl.setAttribute('data-initial-value', String(gatewayEl.value || '').trim());
    gatewayEl.setAttribute('data-dirty', '0');
    gatewayEl.addEventListener('input', function(){
      var current = String(gatewayEl.value || '').trim();
      var initial = String(gatewayEl.getAttribute('data-initial-value') || '').trim();
      gatewayEl.setAttribute('data-dirty', current !== initial ? '1' : '0');
    });
  }
  syncRoutePolicyInterfaceSelectors();
  bindModalForm('routePolicyForm', function(fd){ saveRoutePolicyForm(fd, policyId); });
};

window.deleteRoutePolicyFlow = async function deleteRoutePolicyFlow(policyId){
  var policy = policyById(policyId);
  if(!confirm('Delete route policy ' + (policy ? policy.name : policyId) + '?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/route-policies/' + encodeURIComponent(policyId), { method:'DELETE' });
    pushEv('policy.deleted', 'route policy deleted');
    await refreshPolicies();
  }catch(err){
    pushEv('policy.delete.error', 'route policy delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionRoutePolicyApply = async function actionRoutePolicyApply(policyId){
  try{
    var policy = policyById(policyId);
    var job = await apiFetch(API_PREFIX + '/route-policies/' + encodeURIComponent(policyId) + '/apply', { method:'POST', body:{} });
    pushEv('job.created', 'route policy apply queued for ' + (policy ? policy.name : policyId) + ' [' + job.id + ']');
    showToast('Route policy apply queued: ' + (policy ? policy.name : policyId) + ' [' + job.id + ']', 'success', 'Job queued');
    await refreshJobs();
  }catch(err){
    pushEv('policy.apply.error', 'route policy apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionRoutePolicyTest = async function actionRoutePolicyTest(policyId){
  try{
    var policy = policyById(policyId);
    var result = await apiFetch(API_PREFIX + '/route-policies/' + encodeURIComponent(policyId) + '/test-apply', {
      method:'POST',
      body:{duration_seconds:120}
    });
    pushEv('policy.test_applied', result && result.message ? result.message : ('safe test applied for ' + (policy ? policy.name : policyId)));
    var message = (result && result.message ? result.message : ('Safe test applied for ' + (policy ? policy.name : policyId)));
    if(result){
      message += '\n\nRuntime ids: table ' + String(result.table_id) + ', fwmark ' + String(result.firewall_mark) + ', priority ' + String(result.rule_priority);
      message += '\nTest target: nslookup google.com 8.8.8.8';
    }
    showToast(message, 'success', 'Safe test 2m');
  }catch(err){
    pushEv('policy.test_apply.error', 'route policy safe test failed: ' + (err && err.message ? err.message : err));
    showToast(err && err.message ? err.message : String(err), 'error', 'Safe test failed');
  }
};

function dnsPolicySuggestedTarget(routePolicyId){
  var routePolicy = policyById(routePolicyId);
  if(!routePolicy){
    return { value:'', hint:'Select a route policy first.' };
  }
  var detected = window.nodeDetectedAghDetails ? window.nodeDetectedAghDetails(routePolicy.nid) : null;
  if(!detected){
    return { value:'', hint:'Probe SSH has not detected AdGuard Home on this node yet. Enter the DNS listener IPv4 manually.' };
  }
  var host = String(detected.dns_host || '').trim();
  var port = parseInt(detected.dns_port, 10);
  if(!(port > 0)){ port = 53; }
  if(!host){
    return { value:'', hint:'AdGuard Home was detected, but its DNS bind host was not found in AdGuardHome.yaml. Enter the DNS listener IPv4 manually.' };
  }
  var raw = host + ':' + port;
  if(host === '0.0.0.0' || host === '::' || host === '[::]'){
    return { value:'', hint:'Detected AGH DNS listener ' + raw + '. This is a wildcard bind, so enter the concrete node-local IPv4 manually.' };
  }
  if(!/^(?:\d{1,3}\.){3}\d{1,3}$/.test(host)){
    return { value:'', hint:'Detected AGH DNS listener ' + raw + '. DNS Policy v1 accepts only IPv4, so enter a concrete IPv4 manually.' };
  }
  return { value: raw, hint:'Autofilled from the latest Probe SSH snapshot of AdGuard Home.' };
}

function syncDNSPolicyDetectedTarget(){
  var routeEl = document.getElementById('route_policy_id');
  var dnsEl = document.getElementById('dns_address');
  var hintEl = document.getElementById('dnsPolicyDetectedHint');
  if(!routeEl || !dnsEl){ return; }
  var suggestion = dnsPolicySuggestedTarget(routeEl.value);
  if(hintEl){ hintEl.textContent = suggestion.hint; }
  if(dnsEl.getAttribute('data-autofill') !== '1'){ return; }
  if(dnsEl.getAttribute('data-dirty') === '1'){ return; }
  dnsEl.value = suggestion.value || '';
  dnsEl.setAttribute('data-initial-value', dnsEl.value);
}

window.openDNSPolicyModal = function openDNSPolicyModal(policyId){
  var policy = policyId ? dnsPolicyById(policyId) : null;
  var routeOptions = POLICIES.map(function(p){ return {value:p.id, label:p.name}; });
  var initialRoutePolicyId = policy ? policy.route_policy_id : (POLICIES[0] ? POLICIES[0].id : '');
  var initialSuggestion = dnsPolicySuggestedTarget(initialRoutePolicyId);
  var initialDnsAddress = policy ? policy.addr : (initialSuggestion.value || '');
  var body = '<form id="dnsPolicyForm"><div class="modal-grid">'
    +formSelect('Route policy', 'route_policy_id', initialRoutePolicyId, routeOptions)
    +formInput('DNS address', 'dns_address', initialDnsAddress, {required:true, help:'Target DNS listener on the selected node. Use the actual AGH DNS bind IPv4:port, not the web UI port.'})
    +'<div class="mf-row full"><div class="mf-help" id="dnsPolicyDetectedHint">' + esc(initialSuggestion.hint) + '</div></div>'
    +formCheckbox('Enabled', 'enabled', policy ? policy.on : false, {caption:'DNS interception enabled'})
    +formTextarea('Capture protocols (CSV)', 'capture_protocols', policy ? (policy.capture_protocols || []).join(',') : 'udp', {full:false})
    +formTextarea('Capture ports (CSV)', 'capture_ports', policy ? (policy.capture_ports || []).join(',') : '53', {full:false})
    +formTextarea('Exceptions networks (CSV)', 'exceptions_networks', policy ? (policy.exceptions_networks || []).join(',') : '', {full:true})
    +'</div></form>';
  openModal(policy ? 'Edit DNS Policy' : 'Create DNS Policy', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: policy ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('dnsPolicyForm').requestSubmit(); }}
    ]
  });
  var routeEl = document.getElementById('route_policy_id');
  var dnsEl = document.getElementById('dns_address');
  if(dnsEl){
    dnsEl.setAttribute('data-initial-value', String(dnsEl.value || '').trim());
    dnsEl.setAttribute('data-dirty', '0');
    dnsEl.setAttribute('data-autofill', policy ? '0' : '1');
    dnsEl.addEventListener('input', function(){
      var current = String(dnsEl.value || '').trim();
      var initial = String(dnsEl.getAttribute('data-initial-value') || '').trim();
      dnsEl.setAttribute('data-dirty', current !== initial ? '1' : '0');
    });
  }
  if(routeEl){ routeEl.addEventListener('change', syncDNSPolicyDetectedTarget); }
  syncDNSPolicyDetectedTarget();
  bindModalForm('dnsPolicyForm', function(fd){ saveDNSPolicyForm(fd, policyId); });
};

window.deleteDNSPolicyFlow = async function deleteDNSPolicyFlow(policyId){
  if(!confirm('Delete DNS policy?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/dns-policies/' + encodeURIComponent(policyId), { method:'DELETE' });
    pushEv('dns.deleted', 'dns policy deleted');
    await refreshPolicies();
  }catch(err){
    pushEv('dns.delete.error', 'dns policy delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionDNSPolicyApply = async function actionDNSPolicyApply(policyId){
  try{
    var job = await apiFetch(API_PREFIX + '/dns-policies/' + encodeURIComponent(policyId) + '/apply', { method:'POST', body:{} });
    pushEv('job.created', 'dns policy apply queued [' + job.id + ']');
    await refreshJobs();
  }catch(err){
    pushEv('dns.apply.error', 'dns policy apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.openGeoPolicyModal = function openGeoPolicyModal(policyId){
  var policy = policyId ? geoPolicyById(policyId) : null;
  var routeOptions = POLICIES.map(function(p){ return {value:p.id, label:p.name}; });
  var body = '<form id="geoPolicyForm"><div class="modal-grid">'
    +formSelect('Route policy', 'route_policy_id', policy ? policy.route_policy_id : (POLICIES[0] ? POLICIES[0].id : ''), routeOptions)
    +formInput('Country code', 'country_code', policy ? policy.country_code : '', {required:true, placeholder:'RU'})
    +formSelect('Mode', 'mode', policy ? policy.mode : 'direct', ['direct','multihop'])
    +formCheckbox('Enabled', 'enabled', policy ? policy.enabled : true, {caption:'Geo rule enabled'})
    +formTextarea('Source URL template', 'source_url_template', policy ? policy.source_url_template : 'https://www.ipdeny.com/ipblocks/data/aggregated/{country}-aggregated.zone', {full:true})
    +'</div></form>';
  openModal(policy ? 'Edit Geo Policy' : 'Create Geo Policy', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: policy ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('geoPolicyForm').requestSubmit(); }}
    ]
  });
  bindModalForm('geoPolicyForm', function(fd){ saveGeoPolicyForm(fd, policyId); });
};

window.deleteGeoPolicyFlow = async function deleteGeoPolicyFlow(policyId){
  if(!confirm('Delete geo policy?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/geo-policies/' + encodeURIComponent(policyId), { method:'DELETE' });
    pushEv('geo.deleted', 'geo policy deleted');
    await refreshPolicies();
  }catch(err){
    pushEv('geo.delete.error', 'geo policy delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionGeoPolicyApply = async function actionGeoPolicyApply(policyId){
  try{
    var job = await apiFetch(API_PREFIX + '/geo-policies/' + encodeURIComponent(policyId) + '/apply', { method:'POST', body:{} });
    pushEv('job.created', 'geo policy apply queued [' + job.id + ']');
    await refreshJobs();
  }catch(err){
    pushEv('geo.apply.error', 'geo policy apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.openBalancerModal = function openBalancerModal(balancerId){
  var balancer = balancerId ? balancerById(balancerId) : null;
  var nodeOptions = NODES.map(function(n){ return {value:n.id, label:n.name}; });
  var body = '<form id="balancerForm"><div class="modal-grid">'
    +formSelect('Node', 'node_id', balancer ? balancer.node_id : (NODES[0] ? NODES[0].id : ''), nodeOptions)
    +formInput('Name', 'name', balancer ? balancer.name : '', {required:true})
    +formSelect('Method', 'method', balancer ? balancer.method : 'random', ['random','leastload','leastping'])
    +formCheckbox('Enabled', 'enabled', balancer ? balancer.enabled : true, {caption:'Balancer enabled'})
    +formTextarea('Members', 'members', balancer ? membersToText(balancer.members) : '', {full:true, help:'One member per line: interface_name,gateway,ping_target,weight'})
    +'</div></form>';
  openModal(balancer ? 'Edit Balancer' : 'Create Balancer', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: balancer ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('balancerForm').requestSubmit(); }}
    ]
  });
  bindModalForm('balancerForm', function(fd){ saveBalancerForm(fd, balancerId); });
};

window.deleteBalancerFlow = async function deleteBalancerFlow(balancerId){
  var balancer = balancerById(balancerId);
  if(!confirm('Delete balancer ' + (balancer ? balancer.name : balancerId) + '?')){ return; }
  try{
    await apiFetch(API_PREFIX + '/balancers/' + encodeURIComponent(balancerId), { method:'DELETE' });
    pushEv('balancer.deleted', 'balancer deleted');
    await refreshPolicies();
  }catch(err){
    pushEv('balancer.delete.error', 'balancer delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionBalancerPick = async function actionBalancerPick(balancerId){
  try{
    var result = await apiFetch(API_PREFIX + '/balancers/' + encodeURIComponent(balancerId) + '/pick', { method:'POST', body:{} });
    pushEv('balancer.pick', 'pick -> ' + result.interface_name + (result.gateway ? (' via ' + result.gateway) : ''));
  }catch(err){
    pushEv('balancer.pick.error', 'balancer pick failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

export {};
