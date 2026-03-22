// Page module - all functions exposed as window globals

window.refreshTransitPolicies = async function refreshTransitPolicies(){
  try{
    var data = await apiFetch(API_PREFIX + '/transit-policies');
    TRANSIT_POLICIES = Array.isArray(data) ? data : [];
  }catch(e){
    if(!TRANSIT_POLICIES.length) TRANSIT_POLICIES = [];
  }
  window.renderTransitPolicies();
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

window.renderPolicyTransitHub = function renderPolicyTransitHub(){
  var selectEl = document.getElementById('policyTransitXraySelect');
  var summaryEl = document.getElementById('routingSummaryContent') || document.getElementById('policyTransitSummary');
  if(selectEl){
    var currentValue = selectEl.value;
    var options = ['<option value="">select XRAY service</option>'].concat(
      XRAY_SERVICES.map(function(service){
        return '<option value="'+esc(service.id)+'" '+(String(service.id)===String(currentValue) ? 'selected' : '')+'>'+esc(service.name + ' @ ' + nById(service.node_id).name)+'</option>';
      })
    );
    selectEl.innerHTML = options.join('');
    if(currentValue && !XRAY_SERVICES.some(function(service){ return service.id === currentValue; })){
      selectEl.value = '';
    }
  }
  if(summaryEl){
    var activeStates = {active:1,running:1,succeeded:1,success:1};
    function countActive(arr){ return arr.filter(function(s){ return activeStates[String(s.state||'').toLowerCase()]; }).length; }
    var nodesReachable = NODES.filter(function(n){ return String(n.status||'').toLowerCase()==='reachable'; }).length;
    var linksActive   = LINKS.filter(function(l){ return String(l.state||'').toLowerCase()==='active'; }).length;
    var transitAttached = TRANSIT_POLICIES.filter(function(p){ return p.ingress_service_kind==='xray_service' && p.ingress_service_ref_id; }).length;
    var nextHopKinds = TRANSIT_POLICIES.reduce(function(acc,p){
      transitCandidateSpecs(p).forEach(function(c){ acc[c.kind]=(acc[c.kind]||0)+1; });
      return acc;
    }, {});
    var awgHops  = nextHopKinds.awg_service || 0;
    var wgHops   = nextHopKinds.wg_service  || 0;
    var lnkHops  = nextHopKinds.link        || 0;

    function cnt(total, active, label){
      if(!total) return '0';
      return total + ' (' + active + ' ' + label + ')';
    }
    summaryEl.innerHTML =
      '<div class="stitle" style="margin-bottom:8px">Infrastructure</div>'
      + rows([
          ['Nodes',     cnt(NODES.length,   nodesReachable, 'reachable')],
          ['Links',     cnt(LINKS.length,   linksActive,    'active')],
          ['Balancers', String(BALANCERS.length)],
        ])
      + '<div class="stitle" style="margin:14px 0 8px">Services</div>'
      + rows([
          ['AWG',           cnt(AWG_SERVICES.length,        countActive(AWG_SERVICES),        'active')],
          ['WireGuard',     cnt(WG_SERVICES.length,         countActive(WG_SERVICES),         'active')],
          ['OpenVPN+Cloak', cnt(OVPN_CLOAK_SERVICES.length, countActive(OVPN_CLOAK_SERVICES), 'active')],
          ['XRAY',          cnt(XRAY_SERVICES.length,       countActive(XRAY_SERVICES),       'active')],
        ])
      + '<div class="stitle" style="margin:14px 0 8px">Policies</div>'
      + rows([
          ['Route Policies',   cnt(POLICIES.length,       POLICIES.filter(function(p){ return p.on; }).length,      'enabled')],
          ['DNS Policies',     cnt(DNS_P.length,          DNS_P.filter(function(p){ return p.on; }).length,          'enabled')],
          ['Geo Policies',     cnt(GEO_P.length,          GEO_P.filter(function(p){ return p.enabled; }).length,     'enabled')],
          ['Transit Policies', cnt(TRANSIT_POLICIES.length, transitAttached, 'linked to XRAY')],
        ])
      + '<div class="stitle" style="margin:14px 0 8px">Transit Next Hops</div>'
      + rows([
          ['AWG next hops',  String(awgHops)],
          ['WG next hops',   String(wgHops)],
          ['Link next hops', String(lnkHops)],
        ]);
  }
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
    +formSelect('Primary target', 'primary_next_hop_ref_id', primaryCandidate.ref_id || '', transitNextHopOptions(primaryCandidate.kind || '', defaultNodeId), {help:'Same-node AWG/WG service or attached link.'})
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
    if(policy){ window.showTransitPolicy(policyId); }
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

export { refreshTransitPolicies, renderTransitPolicies, renderPolicyTransitHub, showTransitPolicy, openTransitPolicyModal, deleteTransitPolicyFlow, actionTransitApply, actionTransitPreview };
