// Page module - all functions exposed as window globals

window.transitPoliciesForXray = function transitPoliciesForXray(serviceId){
  return TRANSIT_POLICIES.filter(function(policy){
    return policy.ingress_service_kind === 'xray_service' && policy.ingress_service_ref_id === serviceId;
  });
};

window.transitServiceCount = function transitServiceCount(serviceId){
  return transitPoliciesForXray(serviceId).length;
};

window.transitCandidateSpecs = function transitCandidateSpecs(policy){
  var candidates = Array.isArray(policy && policy.next_hop_candidates_json) ? policy.next_hop_candidates_json.filter(function(item){
    return item && item.kind && item.ref_id;
  }).map(function(item){
    return {kind:String(item.kind), ref_id:String(item.ref_id)};
  }) : [];
  if(candidates.length) return candidates;
  if(policy && policy.next_hop_kind && policy.next_hop_ref_id){
    return [{kind:String(policy.next_hop_kind), ref_id:String(policy.next_hop_ref_id)}];
  }
  return [];
};

window.transitResolveNextHopLabel = function transitResolveNextHopLabel(kind, refId){
  var normalizedKind = String(kind || '').trim().toLowerCase();
  var normalizedRefId = String(refId || '').trim();
  if(!normalizedKind || !normalizedRefId) return '-';
  if(normalizedKind === 'awg_service'){
    var awg = awgServiceById(normalizedRefId);
    return awg ? (awg.name + ' @ ' + nById(awg.node_id).name) : normalizedRefId;
  }
  if(normalizedKind === 'wg_service'){
    var wg = wgServiceById(normalizedRefId);
    return wg ? (wg.name + ' @ ' + nById(wg.node_id).name) : normalizedRefId;
  }
  if(normalizedKind === 'xray_service'){
    var xray = xrayServiceById(normalizedRefId);
    return xray ? (xray.name + ' @ ' + nById(xray.node_id).name) : normalizedRefId;
  }
  if(normalizedKind === 'link'){
    var link = linkById(normalizedRefId);
    return link ? link.name : normalizedRefId;
  }
  return normalizedKind + ':' + normalizedRefId;
};

window.transitNextHopLabel = function transitNextHopLabel(policy){
  var candidates = transitCandidateSpecs(policy);
  return candidates.length ? transitResolveNextHopLabel(candidates[0].kind, candidates[0].ref_id) : '-';
};

window.transitStandbyNextHopLabel = function transitStandbyNextHopLabel(policy){
  var candidates = transitCandidateSpecs(policy).slice(1);
  return candidates.length ? candidates.map(function(candidate){
    return transitResolveNextHopLabel(candidate.kind, candidate.ref_id);
  }).join(', ') : '-';
};

window.transitNextHopChainLabel = function transitNextHopChainLabel(policy){
  var candidates = transitCandidateSpecs(policy);
  return candidates.length ? candidates.map(function(candidate){
    return transitResolveNextHopLabel(candidate.kind, candidate.ref_id);
  }).join(' -> ') : '-';
};

window.transitNextHopSummary = function transitNextHopSummary(policy){
  var primary = transitNextHopLabel(policy);
  var standby = transitStandbyNextHopLabel(policy);
  return standby !== '-' ? (primary + ' | ' + standby) : primary;
};

window.transitNextHopOptions = function transitNextHopOptions(kind, nodeId){
  var normalizedKind = String(kind || '').trim().toLowerCase();
  var currentNodeId = String(nodeId || '').trim();
  if(normalizedKind === 'awg_service'){
    return AWG_SERVICES
      .filter(function(service){ return String(service.node_id) === currentNodeId; })
      .map(function(service){ return {value:service.id, label:service.name + ' @ ' + nById(service.node_id).name}; });
  }
  if(normalizedKind === 'wg_service'){
    return WG_SERVICES
      .filter(function(service){ return String(service.node_id) === currentNodeId; })
      .map(function(service){ return {value:service.id, label:service.name + ' @ ' + nById(service.node_id).name}; });
  }
  if(normalizedKind === 'xray_service'){
    return XRAY_SERVICES
      .filter(function(service){ return String(service.node_id) !== currentNodeId; })
      .map(function(service){ return {value:service.id, label:service.name + ' @ ' + nById(service.node_id).name}; });
  }
  if(normalizedKind === 'link'){
    return LINKS
      .filter(function(link){
        return Array.isArray(link.endpoints_json) && link.endpoints_json.some(function(endpoint){
          return endpoint && String(endpoint.node_id) === currentNodeId;
        });
      })
      .map(function(link){ return {value:link.id, label:link.name}; });
  }
  return [];
};

window.transitNextHopOptionsHtml = function transitNextHopOptionsHtml(kind, nodeId, currentValue){
  var options = transitNextHopOptions(kind, nodeId);
  var current = String(currentValue || '').trim();
  if(current && !options.some(function(item){ return String(item.value) === current; })){
    options.unshift({value:current, label:transitResolveNextHopLabel(kind, current) + ' (saved)'});
  }
  if(!options.length){
    options = [{value:'', label:'No matching targets'}];
  }else{
    options.unshift({value:'', label:'None'});
  }
  return options.map(function(opt){
    return '<option value="'+esc(opt.value)+'" '+(String(opt.value)===current ? 'selected' : '')+'>'+esc(opt.label)+'</option>';
  }).join('');
};

window.saveTransitPolicyForm = async function saveTransitPolicyForm(fd, policyId){
  function intField(value){
    var trimmed = String(value == null ? '' : value).trim();
    if(!trimmed) return null;
    var parsed = parseInt(trimmed, 10);
    return isNaN(parsed) ? null : parsed;
  }
  function splitCsv(value){
    return String(value == null ? '' : value)
      .split(',')
      .map(function(item){ return String(item || '').trim(); })
      .filter(Boolean);
  }
  function splitCsvInts(value){
    return splitCsv(value).map(function(item){ return parseInt(item, 10); }).filter(function(item){ return !isNaN(item); });
  }
  function nullableText(value){
    var trimmed = String(value == null ? '' : value).trim();
    return trimmed ? trimmed : null;
  }
  function candidate(prefix){
    var kind = nullableText(fd.get(prefix + '_kind'));
    var refId = nullableText(fd.get(prefix + '_ref_id'));
    return kind && refId ? {kind:kind, ref_id:refId} : null;
  }

  var candidates = ['primary_next_hop', 'standby_next_hop', 'backup_next_hop']
    .map(candidate)
    .filter(Boolean)
    .filter(function(item, index, arr){
      return arr.findIndex(function(other){
        return other.kind === item.kind && other.ref_id === item.ref_id;
      }) === index;
    });

  var payload = {
    name: String(fd.get('name') || '').trim(),
    node_id: String(fd.get('node_id') || '').trim(),
    ingress_interface: String(fd.get('ingress_interface') || '').trim(),
    enabled: fd.get('enabled') === 'on',
    transparent_port: intField(fd.get('transparent_port')),
    firewall_mark: intField(fd.get('firewall_mark')),
    route_table_id: intField(fd.get('route_table_id')),
    rule_priority: intField(fd.get('rule_priority')),
    ingress_service_kind: nullableText(fd.get('ingress_service_kind')),
    ingress_service_ref_id: nullableText(fd.get('ingress_service_ref_id')),
    next_hop_kind: candidates[0] ? candidates[0].kind : null,
    next_hop_ref_id: candidates[0] ? candidates[0].ref_id : null,
    next_hop_candidates_json: candidates,
    capture_protocols_json: splitCsv(fd.get('capture_protocols_json')),
    capture_cidrs_json: splitCsv(fd.get('capture_cidrs_json')),
    excluded_cidrs_json: splitCsv(fd.get('excluded_cidrs_json')),
    management_bypass_ipv4_json: splitCsv(fd.get('management_bypass_ipv4_json')),
    management_bypass_tcp_ports_json: splitCsvInts(fd.get('management_bypass_tcp_ports_json')),
  };
  var applyAfterSave = fd.get('apply_after_save') === '1';
  try{
    var saved;
    if(policyId){
      saved = await apiFetch(API_PREFIX + '/transit-policies/' + encodeURIComponent(policyId), {method:'PATCH', body:payload});
    }else{
      saved = await apiFetch(API_PREFIX + '/transit-policies', {method:'POST', body:payload});
    }
    if(applyAfterSave && saved && saved.id){
      await apiFetch(API_PREFIX + '/transit-policies/' + encodeURIComponent(saved.id) + '/apply', {method:'POST', body:{}});
    }
    closeModal();
    await Promise.all([refreshTransitPolicies(), refreshXrayServices()]);
    if(saved && saved.id){
      showTransitPolicy(saved.id);
    }
  }catch(err){
    alert(err && err.message ? err.message : String(err));
  }
};

window.refreshTransitPolicies = async function refreshTransitPolicies(){
  try{
    var data = await apiFetch(API_PREFIX + '/transit-policies');
    TRANSIT_POLICIES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!TRANSIT_POLICIES.length) TRANSIT_POLICIES = [];
  }
  renderTransitPolicies();
  renderXrayServices();
  renderPolicyTransitHub();
};

window.renderTransitPolicies = function renderTransitPolicies(){
  var tb = document.getElementById('transittb');
  if(!tb) return;
  if(!TRANSIT_POLICIES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="9">No transit policies.</td></tr>';
    return;
  }
  tb.innerHTML = TRANSIT_POLICIES.map(function(policy){
    var capture = (policy.capture_protocols_json || []).join('/') + ' -> ' + ((policy.capture_cidrs_json || []).join(', ') || '-');
    var health = policy.health_summary_json || {};
    var xrayLabel = '-';
    if(policy.ingress_service_kind === 'xray_service'){
      var svc = xrayServiceById(policy.ingress_service_ref_id);
      xrayLabel = svc ? svc.name : (policy.ingress_service_ref_id || '-');
    }
    return '<tr onclick="showTransitPolicy(\''+esc(policy.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(policy.name)+'</td>'
      +'<td>'+esc(nById(policy.node_id).name)+'</td>'
      +'<td class="m">'+esc(policy.ingress_interface || '-')+'</td>'
      +'<td class="m">'+esc(capture)+'</td>'
      +'<td class="m">'+esc(String(policy.transparent_port))+' / '+esc(String(policy.firewall_mark))+'</td>'
      +'<td class="m">'+esc(xrayLabel)+'</td>'
      +'<td class="m">'+esc(transitNextHopSummary(policy))+'</td>'
      +'<td>'+sp(health.status || policy.state)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();actionTransitPreview(\''+esc(policy.id)+'\')">PREVIEW</button>'
        +'<button class="btn sm pri" onclick="event.stopPropagation();actionTransitApply(\''+esc(policy.id)+'\')">APPLY</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();openTransitPolicyModal(\''+esc(policy.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();deleteTransitPolicyFlow(\''+esc(policy.id)+'\')">DEL</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.showTransitPolicy = function showTransitPolicy(id){
  var policy = transitPolicyById(id);
  if(!policy) return;
  var xrayService = policy.ingress_service_kind === 'xray_service' ? xrayServiceById(policy.ingress_service_ref_id) : null;
  var health = policy.health_summary_json || {};
  var nextHop = health.next_hop || (policy.applied_config_json && policy.applied_config_json.next_hop) || null;
  var xrayAttachment = health.xray_attachment || null;
  openDP('Transit ' + policy.name,
    rows([
      ['ID', policy.id],
      ['Node', nById(policy.node_id).name],
      ['State', policy.state || '-'],
      ['Health', health.status || '-'],
      ['Enabled', policy.enabled ? 'yes' : 'no'],
      ['Ingress Interface', policy.ingress_interface || '-'],
      ['Transparent Port', String(policy.transparent_port || '-')],
      ['Firewall Mark', String(policy.firewall_mark || '-')],
      ['Route Table', String(policy.route_table_id || '-')],
      ['Rule Priority', String(policy.rule_priority || '-')],
      ['Capture Protocols', (policy.capture_protocols_json || []).join(', ') || '-'],
      ['Capture CIDRs', (policy.capture_cidrs_json || []).join(', ') || '-'],
      ['Excluded CIDRs', (policy.excluded_cidrs_json || []).join(', ') || '-'],
      ['Bypass IPv4', (policy.management_bypass_ipv4_json || []).join(', ') || '-'],
      ['Bypass TCP Ports', (policy.management_bypass_tcp_ports_json || []).join(', ') || '-'],
      ['XRAY Service', xrayService ? xrayService.name : (policy.ingress_service_ref_id || '-')],
      ['Active Next Hop', transitNextHopLabel(policy)],
      ['Next Hop Chain', transitNextHopChainLabel(policy)],
      ['Standby Next Hops', transitStandbyNextHopLabel(policy)],
      ['Next Hop Interface', nextHop && nextHop.interface_name ? nextHop.interface_name : '-'],
      ['Next Hop Source IP', nextHop && nextHop.source_ip ? nextHop.source_ip : '-'],
      ['Next Hop Table', nextHop && nextHop.egress_table_id != null ? String(nextHop.egress_table_id) : '-'],
      ['Next Hop Priority', nextHop && nextHop.egress_rule_priority != null ? String(nextHop.egress_rule_priority) : '-'],
      ['XRAY Attached', xrayAttachment ? (xrayAttachment.attached ? 'yes' : 'no') : '-'],
      ['XRAY State', xrayAttachment && xrayAttachment.state ? xrayAttachment.state : '-'],
      ['Chain', health.chain_name || ((policy.applied_config_json || {}).chain_name) || '-'],
      ['Config Path', health.config_path || ((policy.applied_config_json || {}).config_path) || '-'],
      ['Applied At', health.applied_at ? fmtDate(health.applied_at) : '-'],
      ['Last Error', policy.last_error_text || '-']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="actionTransitPreview(\''+esc(policy.id)+'\')">PREVIEW</button>'
      +'<button class="btn pri" onclick="actionTransitApply(\''+esc(policy.id)+'\')">APPLY</button>'
      +'<button class="btn" onclick="openTransitPolicyModal(\''+esc(policy.id)+'\')">EDIT</button>'
      +'<button class="btn red" onclick="deleteTransitPolicyFlow(\''+esc(policy.id)+'\')">DELETE</button>'
    +'</div>'
  );
};

window.openTransitPolicyModal = function openTransitPolicyModal(policyId, presetXrayServiceId){
  var policy = policyId ? transitPolicyById(policyId) : null;
  var presetXray = presetXrayServiceId ? xrayServiceById(presetXrayServiceId) : null;
  var defaultNodeId = policy ? policy.node_id : (presetXray ? presetXray.node_id : (NODES[0] ? NODES[0].id : ''));
  var nodeOptions = NODES.map(function(node){ return {value:node.id, label:node.name}; });
  var candidates = transitCandidateSpecs(policy);
  var primaryCandidate = candidates[0] || {};
  var standbyCandidate = candidates[1] || {};
  var backupCandidate = candidates[2] || {};
  var xrayOptions = [{value:'', label:'None'}].concat(XRAY_SERVICES.map(function(service){
    return {value:service.id, label:service.name + ' — ' + nById(service.node_id).name};
  }));
  var nextHopKindOptions = [
    {value:'', label:'None'},
    {value:'awg_service', label:'AWG Service'},
    {value:'wg_service', label:'WG Service'},
    {value:'xray_service', label:'XRAY Service'},
    {value:'link', label:'Link'},
  ];
  var body = '<form id="transitPolicyForm"><div class="modal-grid">'
    +formInput('Name', 'name', policy ? policy.name : (presetXray ? (presetXray.name + '-transit') : ''), {required:true})
    +formSelect('Node', 'node_id', defaultNodeId, nodeOptions, {help:'Managed node where TPROXY runtime will live.'})
    +formInput('Ingress interface', 'ingress_interface', policy ? policy.ingress_interface : 'eth0', {required:true})
    +formCheckbox('Enabled', 'enabled', policy ? !!policy.enabled : true, {caption:'Keep transit policy active after save'})
    +formInput('Transparent port', 'transparent_port', policy ? String(policy.transparent_port) : '15001', {type:'number', required:true})
    +formInput('Firewall mark', 'firewall_mark', policy && policy.firewall_mark != null ? String(policy.firewall_mark) : '', {type:'number', placeholder:'auto'})
    +formInput('Route table', 'route_table_id', policy && policy.route_table_id != null ? String(policy.route_table_id) : '', {type:'number', placeholder:'auto'})
    +formInput('Rule priority', 'rule_priority', policy && policy.rule_priority != null ? String(policy.rule_priority) : '', {type:'number', placeholder:'auto'})
    +formSelect('XRAY Service', 'ingress_service_ref_id', policy ? (policy.ingress_service_ref_id || '') : (presetXrayServiceId || ''), xrayOptions, {help:'Optional XRAY service that will receive transparent traffic.'})
    +formInput('Ingress kind', 'ingress_service_kind', policy ? (policy.ingress_service_kind || '') : (presetXrayServiceId ? 'xray_service' : ''), {readonly:!!presetXrayServiceId, placeholder:'xray_service'})
    +formSelect('Primary next hop', 'primary_next_hop_kind', primaryCandidate.kind || '', nextHopKindOptions, {help:'Preferred kernel egress target for XRAY transparent outbound.'})
    +formSelect('Primary target', 'primary_next_hop_ref_id', primaryCandidate.ref_id || '', transitNextHopOptions(primaryCandidate.kind || '', defaultNodeId), {help:'Same-node AWG/WG service, remote XRAY service, or attached link.'})
    +formSelect('Standby next hop', 'standby_next_hop_kind', standbyCandidate.kind || '', nextHopKindOptions, {help:'Optional first failover target.'})
    +formSelect('Standby target', 'standby_next_hop_ref_id', standbyCandidate.ref_id || '', transitNextHopOptions(standbyCandidate.kind || '', defaultNodeId), {help:'Optional first backup path.'})
    +formSelect('Backup next hop', 'backup_next_hop_kind', backupCandidate.kind || '', nextHopKindOptions, {help:'Optional second failover target.'})
    +formSelect('Backup target', 'backup_next_hop_ref_id', backupCandidate.ref_id || '', transitNextHopOptions(backupCandidate.kind || '', defaultNodeId), {help:'Optional second backup path.'})
    +formTextarea('Capture protocols', 'capture_protocols_json', policy ? (policy.capture_protocols_json || []).join(', ') : 'tcp, udp', {help:'Comma-separated. Current foundation supports tcp, udp.'})
    +formTextarea('Capture CIDRs', 'capture_cidrs_json', policy ? (policy.capture_cidrs_json || []).join(', ') : '0.0.0.0/0', {help:'Destination CIDRs to transparently capture.'})
    +formTextarea('Excluded CIDRs', 'excluded_cidrs_json', policy ? (policy.excluded_cidrs_json || []).join(', ') : '', {help:'Excluded destination CIDRs.'})
    +formTextarea('Bypass IPv4', 'management_bypass_ipv4_json', policy ? (policy.management_bypass_ipv4_json || []).join(', ') : '', {help:'Extra management subnets to bypass before TPROXY.'})
    +formTextarea('Bypass TCP ports', 'management_bypass_tcp_ports_json', policy ? (policy.management_bypass_tcp_ports_json || []).join(', ') : '', {help:'Local TCP ports protected from capture. Empty keeps auto defaults.'})
    +'</div></form>';
  openModal(policy ? 'Edit Transit Policy' : 'Create Transit Policy', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Save', className:'btn', onClick:function(){ document.getElementById('transitPolicyForm').requestSubmit(); }},
      {label:'Save + Apply', className:'btn pri', onClick:function(){ document.getElementById('transitApplyAfterSave').value = '1'; document.getElementById('transitPolicyForm').requestSubmit(); }}
    ]
  });
  var hidden = document.createElement('input');
  hidden.type = 'hidden';
  hidden.name = 'apply_after_save';
  hidden.id = 'transitApplyAfterSave';
  hidden.value = '0';
  document.getElementById('transitPolicyForm').appendChild(hidden);
  function refreshTransitNextHopTargets(prefix){
    var nodeEl = document.getElementById('node_id');
    var kindEl = document.getElementById(prefix + '_kind');
    var refEl = document.getElementById(prefix + '_ref_id');
    if(!nodeEl || !kindEl || !refEl) return;
    var currentValue = refEl.value;
    var options = transitNextHopOptions(kindEl.value, nodeEl.value);
    refEl.innerHTML = transitNextHopOptionsHtml(kindEl.value, nodeEl.value, currentValue);
    var stillExists = options.some(function(opt){ return String(opt.value) === String(currentValue); });
    if(!stillExists && options.length){
      refEl.value = '';
    }
  }
  var nodeEl = document.getElementById('node_id');
  if(nodeEl){
    nodeEl.addEventListener('change', function(){
      ['primary_next_hop','standby_next_hop','backup_next_hop'].forEach(refreshTransitNextHopTargets);
    });
  }
  ['primary_next_hop','standby_next_hop','backup_next_hop'].forEach(function(prefix){
    var kindEl = document.getElementById(prefix + '_kind');
    if(kindEl){ kindEl.addEventListener('change', function(){ refreshTransitNextHopTargets(prefix); }); }
  });
  bindModalForm('transitPolicyForm', function(fd){ saveTransitPolicyForm(fd, policyId); });
};

window.deleteTransitPolicyFlow = async function deleteTransitPolicyFlow(policyId){
  var policy = transitPolicyById(policyId);
  if(!confirm('Delete transit policy ' + (policy ? policy.name : policyId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/transit-policies/' + encodeURIComponent(policyId), { method:'DELETE' });
    pushEv('transit_policy.deleted', 'Transit policy deleted: ' + (policy ? policy.name : policyId));
    await Promise.all([refreshTransitPolicies(), refreshXrayServices()]);
    closeDP();
  }catch(err){
    pushEv('transit_policy.error', 'delete failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionTransitApply = async function actionTransitApply(policyId){
  try{
    var policy = transitPolicyById(policyId);
    var applied = await apiFetch(API_PREFIX + '/transit-policies/' + encodeURIComponent(policyId) + '/apply', { method:'POST', body:{} });
    pushEv('transit_policy.applied', 'Transit policy applied: ' + ((applied && applied.name) || (policy && policy.name) || policyId));
    await Promise.all([refreshTransitPolicies(), refreshXrayServices()]);
    if(policy){ showTransitPolicy(policyId); }
  }catch(err){
    pushEv('transit_policy.error', 'apply failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionTransitPreview = async function actionTransitPreview(policyId){
  try{
    var preview = await apiFetch(API_PREFIX + '/transit-policies/' + encodeURIComponent(policyId) + '/preview');
    var rulesHtml = (preview.rules || []).map(function(rule){
      return '<div class="drow"><span class="dk">'+esc(rule.kind + (rule.chain ? ' / ' + rule.chain : ''))+'</span><span class="dv">'+esc(rule.summary)+'</span></div>'
        + '<div class="jlog" style="margin-top:6px;margin-bottom:8px;">'+esc(rule.command)+'</div>';
    }).join('');
    var attachment = preview.xray_attachment || {};
    var nextHop = preview.next_hop_attachment || {};
    var candidates = (preview.next_hop_candidates || []).map(function(item){
      var state = item.attached ? 'active' : (item.available ? (item.state || 'standby') : 'unavailable');
      return '<div class="drow"><span class="dk">#'+esc(String((item.candidate_index || 0) + 1))+'</span><span class="dv">'+esc(transitResolveNextHopLabel(item.kind, item.ref_id))+' / '+esc(state)+'</span></div>';
    }).join('');
    var warnings = (preview.warnings || []).map(function(w){
      return '<div class="drow"><span class="dk">Warning</span><span class="dv">'+esc(w)+'</span></div>';
    }).join('');
    openModal('Transit Preview — ' + preview.policy_name,
      '<div class="modal-grid one">'
        + rows([
          ['Unit', preview.unit_name],
          ['Config Path', preview.config_path],
          ['Chain', preview.chain_name],
          ['XRAY Attached', attachment.attached ? 'yes' : 'no'],
          ['XRAY Service', attachment.service_name || '-'],
          ['Inbound Tag', attachment.inbound_tag || '-'],
          ['Route Path', attachment.route_path || '-'],
          ['Active Next Hop', nextHop.display_name || '-'],
          ['Next Hop Interface', nextHop.interface_name || '-'],
          ['Next Hop Source IP', nextHop.source_ip || '-'],
          ['Next Hop Table', nextHop.egress_table_id != null ? String(nextHop.egress_table_id) : '-'],
          ['Next Hop Priority', nextHop.egress_rule_priority != null ? String(nextHop.egress_rule_priority) : '-']
        ])
        + (candidates ? '<div class="stitle">Failover Chain</div><div style="margin-top:8px;">'+candidates+'</div>' : '')
        + (warnings ? '<div class="stitle">Warnings</div><div style="margin-top:8px;">'+warnings+'</div>' : '')
        + '<div class="stitle">Managed Rules</div><div style="margin-top:8px;">'+rulesHtml+'</div>'
      + '</div>',
      {buttons:[{label:'Close', className:'btn', onClick:closeModal}]}
    );
  }catch(err){
    pushEv('transit_policy.error', 'preview failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

export {};
