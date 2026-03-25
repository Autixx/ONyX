// Page module - all functions exposed as window globals

var _SCHED_KEYS   = ['mon','tue','wed','thu','fri','sat','sun'];
var _SCHED_LABELS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

function subscriptionAccessSummary(obj) {
  if(!obj || !obj.access_window_enabled) return 'Always';
  var DAY_NAMES = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  var mask = Number(obj.access_days_mask != null ? obj.access_days_mask : 127);
  var days = DAY_NAMES.filter(function(_,i){ return !!(mask & (1<<i)); });
  var timeStr = '';
  if(obj.access_window_start_local && obj.access_window_end_local){
    timeStr = ' ' + obj.access_window_start_local + '–' + obj.access_window_end_local;
  }
  return days.length === 7 ? ('Every day' + timeStr) : (days.join(', ') + timeStr);
}

window.loadPlans = async function loadPlans(){
  PLANS = await apiFetch(API_PREFIX + '/plans');
  window.renderPlans();
  window.updateUserSubFilter();
};

window.loadSubscriptions = async function loadSubscriptions(){
  SUBSCRIPTIONS = await apiFetch(API_PREFIX + '/subscriptions');
  window.renderSubscriptions();
};

window.loadTransportPackages = async function loadTransportPackages(){
  TRANSPORT_PACKAGES = await apiFetch(API_PREFIX + '/transport-packages');
  window.renderTransportPackages();
};

window.refreshIdentityData = async function refreshIdentityData(){
  await Promise.all([
    loadUsers(),
    loadPlans(),
    loadSubscriptions(),
    loadReferralCodes(),
    loadDevices(),
    loadTransportPackages()
  ]);
};

window.updateUserSubFilter = function updateUserSubFilter(){
  var sel = document.getElementById('userSubFilter');
  if(!sel) return;
  var cur = sel.value;
  sel.innerHTML = '<option value="">All subscriptions</option>'
    + PLANS.map(function(p){ return '<option value="'+esc(p.id)+'"'+(p.id===cur?' selected':'')+'>'+esc(p.name)+'</option>'; }).join('');
};

window.renderPlans = function renderPlans(){
  var tb = document.getElementById('plantb');
  if(!tb) return;
  if(!PLANS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="7">No subscriptions.</td></tr>';
    return;
  }
  tb.innerHTML = PLANS.map(function(p){
    var tpName = '-';
    if(p.transport_package_id){
      var tp = (TRANSPORT_PACKAGES || []).find(function(x){ return x.id === p.transport_package_id; });
      tpName = tp ? (tp.name || tp.id) : p.transport_package_id;
    }
    return '<tr>'
      +'<td class="m">'+esc(p.name)+'</td>'
      +'<td>'+esc(p.billing_mode)+'</td>'
      +'<td>'+esc(tpName)+'</td>'
      +'<td>'+esc(String(p.default_device_limit || '-'))+'</td>'
      +'<td>'+esc(subscriptionAccessSummary(p))+'</td>'
      +'<td>'+(p.enabled ? sp('active') : sp('deleted'))+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="showPlan(\''+esc(p.id)+'\')">VIEW</button>'
        +'<button class="btn sm" onclick="openPlanModal(\''+esc(p.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="deletePlanFlow(\''+esc(p.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.renderSubscriptions = function renderSubscriptions(){
  var tb = document.getElementById('subtb');
  if(!tb) return;
  if(!SUBSCRIPTIONS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="6">No subscriptions.</td></tr>';
    return;
  }
  tb.innerHTML = SUBSCRIPTIONS.map(function(s){
    return '<tr>'
      +'<td class="m">'+esc(userNameById(s.user_id))+'</td>'
      +'<td>'+esc(planNameById(s.plan_id))+'</td>'
      +'<td>'+sp(s.status)+'</td>'
      +'<td>'+esc(s.expires_at ? new Date(s.expires_at).toLocaleString() : 'lifetime')+'</td>'
      +'<td>'+esc(subscriptionAccessSummary(s))+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="showSubscription(\''+esc(s.id)+'\')">VIEW</button>'
        +'<button class="btn sm" onclick="openSubscriptionModal(\''+esc(s.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="deleteSubscriptionFlow(\''+esc(s.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.renderTransportPackages = function renderTransportPackages(){
  var tb = document.getElementById('tptb');
  if(!tb) return;
  if(!TRANSPORT_PACKAGES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="4">No transport packages.</td></tr>';
    return;
  }
  tb.innerHTML = TRANSPORT_PACKAGES.map(function(pkg){
    var enabled = [];
    if(pkg.enable_xray) enabled.push('XRAY');
    if(pkg.enable_awg) enabled.push('AWG');
    if(pkg.enable_wg) enabled.push('WG');
    if(pkg.enable_openvpn_cloak) enabled.push('OVPN');
    return '<tr>'
      +'<td class="m">'+esc(pkg.name || '-')+'</td>'
      +'<td>'+esc(enabled.join(', ') || '-')+'</td>'
      +'<td class="m">'+esc((pkg.priority_order_json || []).join(' > '))+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="showTransportPackage(\''+esc(pkg.id)+'\')">VIEW</button>'
        +'<button class="btn sm" onclick="openTransportPackageModal(\''+esc(pkg.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="deleteTransportPackageFlow(\''+esc(pkg.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showPlan = function showPlan(id){
  var p = planById(id); if(!p) return;
  var tpName = '-';
  if(p.transport_package_id){
    var tp = (TRANSPORT_PACKAGES || []).find(function(x){ return x.id === p.transport_package_id; });
    tpName = tp ? (tp.name || tp.id) : p.transport_package_id;
  }
  openDP('Subscription ' + p.name, rows([
    ['ID', p.id],
    ['Name', p.name],
    ['Billing Mode', p.billing_mode],
    ['Enabled', p.enabled ? 'yes' : 'no'],
    ['Duration Days', p.duration_days != null ? String(p.duration_days) : '-'],
    ['Fixed Expires At', p.fixed_expires_at ? new Date(p.fixed_expires_at).toLocaleString() : '-'],
    ['Device Limit', String(p.default_device_limit || '-')],
    ['Traffic Quota', p.traffic_quota_bytes != null ? String(p.traffic_quota_bytes) + ' B' : '-'],
    ['Speed Limit', p.speed_limit_kbps != null ? String(p.speed_limit_kbps) + ' kbps' : '-'],
    ['Transport Package', tpName],
    ['Access Schedule', subscriptionAccessSummary(p)],
    ['Exception Dates', p.access_exception_dates_json && p.access_exception_dates_json.length ? p.access_exception_dates_json.join(', ') : '-'],
    ['Comment', p.comment || '-'],
    ['Description', p.description || '-']
  ]), { kind:'plan', id:p.id });
};

window.showSubscription = function showSubscription(id){
  var s = subscriptionById(id); if(!s) return;
  openDP('Subscription', rows([
    ['ID', s.id],
    ['User', userNameById(s.user_id)],
    ['Plan', planNameById(s.plan_id)],
    ['Status', s.status],
    ['Billing Mode', s.billing_mode],
    ['Starts', s.starts_at ? new Date(s.starts_at).toLocaleString() : '-'],
    ['Expires', s.expires_at ? new Date(s.expires_at).toLocaleString() : 'lifetime'],
    ['Device Limit', String(s.device_limit || '-')],
    ['Traffic Quota Bytes', s.traffic_quota_bytes != null ? String(s.traffic_quota_bytes) : '-'],
    ['Access Window', subscriptionAccessSummary(s)]
  ]), { kind:'subscription', id:s.id });
};

window.showTransportPackage = function showTransportPackage(id){
  var pkg = transportPackageById(id); if(!pkg) return;
  openDP('Transport Package — ' + (pkg.name || pkg.id), rows([
    ['ID', pkg.id],
    ['Name', pkg.name || '-'],
    ['Enabled', [
      pkg.enable_xray ? 'xray' : null,
      pkg.enable_awg ? 'awg' : null,
      pkg.enable_wg ? 'wg' : null,
      pkg.enable_openvpn_cloak ? 'openvpn_cloak' : null
    ].filter(Boolean).join(', ') || '-'],
    ['Priority', (pkg.priority_order_json || []).join(' > ') || '-'],
    ['Split Tunnel', pkg.split_tunnel_enabled ? 'enabled' : 'disabled'],
    ['Split Routes', (pkg.split_tunnel_routes_json || []).join(', ') || '-']
  ])
  +'<div class="dp-actions">'
    +'<button class="btn" onclick="openTransportPackageModal(\''+esc(pkg.id)+'\')">EDIT</button>'
    +'<button class="btn red" onclick="deleteTransportPackageFlow(\''+esc(pkg.id)+'\')">DEL</button>'
  +'</div>', { kind:'transport-package', id:pkg.id });
};

window.openPlanModal = function openPlanModal(planId){
  var plan = planId ? planById(planId) : null;
  var tpOptions = [{value:'', label:'— none —'}].concat((TRANSPORT_PACKAGES || []).map(function(tp){ return {value:tp.id, label:(tp.name || tp.id)}; }));
  var body = '<form id="planForm"><div class="modal-grid">'
    +formInput('Name', 'name', plan ? plan.name : '', {required:true})
    +(!plan ? formInput('Code (slug)', 'code', '', {required:true, help:'Unique identifier, e.g. basic_monthly'}) : '')
    +formSelect('Billing mode', 'billing_mode', plan ? plan.billing_mode : 'periodic', ['manual','lifetime','periodic','trial','fixed_date'])
    +formCheckbox('Enabled', 'enabled', plan ? plan.enabled : true, {caption:'Subscription enabled'})
    +formInput('Duration days', 'duration_days', plan && plan.duration_days != null ? String(plan.duration_days) : '', {type:'number', help:'For periodic/trial modes'})
    +formInput('Fixed expires at', 'fixed_expires_at', plan && plan.fixed_expires_at ? plan.fixed_expires_at.slice(0,16) : '', {type:'datetime-local', help:'For fixed_date mode'})
    +formInput('Device limit', 'default_device_limit', plan ? String(plan.default_device_limit || 1) : '1', {type:'number', required:true})
    +formInput('Traffic quota bytes', 'traffic_quota_bytes', plan && plan.traffic_quota_bytes != null ? String(plan.traffic_quota_bytes) : '', {type:'number', help:'0 = unlimited'})
    +formInput('Speed limit kbps', 'speed_limit_kbps', plan && plan.speed_limit_kbps != null ? String(plan.speed_limit_kbps) : '', {type:'number', help:'Client-side limit, 0 = unlimited'})
    +formSelect('Transport package', 'transport_package_id', plan ? (plan.transport_package_id || '') : '', tpOptions)
    +(function(){
      var sched = plan ? (plan.access_schedule_json || {}) : {};
      var exDates = plan && plan.access_exception_dates_json ? plan.access_exception_dates_json.join(', ') : '';
      var cols = _SCHED_KEYS.map(function(key, i){
        var d = sched[key] || {};
        return '<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
          +'<div style="font-size:11px;font-weight:700;color:var(--t1);text-align:center;">'+_SCHED_LABELS[i]+'</div>'
          +'<input type="time" name="sched_'+key+'_start" value="'+(d.start||'')+'" style="width:100%;font-size:11px;background:var(--bg1);border:1px solid var(--border);border-radius:4px;padding:2px 3px;color:var(--t0);box-sizing:border-box;" title="Start">'
          +'<input type="time" name="sched_'+key+'_end" value="'+(d.end||'')+'" style="width:100%;font-size:11px;background:var(--bg1);border:1px solid var(--border);border-radius:4px;padding:2px 3px;color:var(--t0);box-sizing:border-box;" title="End">'
          +'</div>';
      }).join('');
      return '<div class="mf-row full" style="border:1px solid var(--border);border-radius:6px;padding:12px 14px;display:flex;flex-direction:column;gap:10px;">'
        +'<div style="font-size:11px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:var(--t1);">Access Schedule</div>'
        +'<label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-size:13px;">'
          +'<input type="checkbox" name="access_window_enabled"'+(plan && plan.access_window_enabled?' checked':'')+'>'
          +'Enable time schedule'
        +'</label>'
        +'<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:6px;">'+cols+'</div>'
        +'<div>'
          +'<div class="mf-label" style="margin-bottom:4px;">Exception dates</div>'
          +'<textarea name="access_exception_dates" rows="2" style="width:100%;box-sizing:border-box;background:var(--bg1);border:1px solid var(--border);border-radius:4px;color:var(--t0);font-size:12px;padding:6px;resize:vertical;">'+esc(exDates)+'</textarea>'
          +'<div style="font-size:11px;color:var(--t2);margin-top:2px;">Comma-separated YYYY-MM-DD dates always blocked (e.g. holidays): 2026-01-01, 2026-05-09</div>'
        +'</div>'
        +'</div>';
    })()
    +formTextarea('Comment', 'comment', plan ? (plan.comment || '') : '', {help:'Free text note'})
    +(plan ? (function(){
      var poolsForPlan = (REFERRAL_POOLS || []).filter(function(p){ return p.plan_id === plan.id; });
      var freePools = (REFERRAL_POOLS || []).filter(function(p){ return !p.plan_id; });
      var poolList = poolsForPlan.length
        ? poolsForPlan.map(function(p){
            return '<span class="pill pg" style="margin-right:4px;">'+esc(p.name)+'</span>'
              +'<span class="muted" style="font-size:11px;">'+esc(String(p.live_codes))+' live, '+esc(String(p.used_codes))+' used</span> ';
          }).join('')
        : '<span class="muted" style="font-size:12px;">no pools assigned</span>';
      var assignRow = freePools.length
        ? '<div style="display:flex;gap:6px;align-items:center;margin-top:8px;flex-wrap:wrap;">'
            +'<select class="mf-select" id="planPoolAssignSelect" style="min-width:160px">'
              +'<option value="">— assign existing pool —</option>'
              +freePools.map(function(p){ return '<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>'; }).join('')
            +'</select>'
            +'<button class="btn sm" type="button" onclick="assignPoolToPlan(\''+esc(plan.id)+'\')">ASSIGN</button>'
          +'</div>'
        : '';
      return '<div class="mf-row full" style="border-top:1px solid var(--border);padding-top:12px;margin-top:4px;">'
        +'<div class="mf-label">Referral Pools</div>'
        +'<div style="margin-top:4px;">'+poolList+'</div>'
        +assignRow
        +'</div>';
    })() : '')
    +'</div></form>';
  var modalButtons = [{label:'Cancel', className:'btn', onClick:closeModal}];
  if(plan){
    modalButtons.push({label:'Create Pool', className:'btn', onClick:function(){ closeModal(); openReferralPoolModal(plan.id); }});
  }
  modalButtons.push({label:plan ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('planForm').requestSubmit(); }});
  openModal(plan ? 'Edit Subscription' : 'New Subscription', body, { buttons: modalButtons });
  bindModalForm('planForm', function(fd){ savePlanForm(fd, planId); });
};

window.openSubscriptionModal = function openSubscriptionModal(subscriptionId){
  var sub = subscriptionId ? subscriptionById(subscriptionId) : null;
  var userOptions = USERS.map(function(u){ return {value:u.id, label:u.username}; });
  var planOptions = [{value:'', label:'-'}].concat(PLANS.map(function(p){ return {value:p.id, label:p.name}; }));
  var dayMask = Number(sub && sub.access_days_mask != null ? sub.access_days_mask : 127);
  function dayBox(idx, label){
    return '<label style=\"display:flex;align-items:center;gap:8px;color:var(--t0);\"><input type=\"checkbox\" name=\"access_day_'+idx+'\" '+((dayMask & (1 << idx)) ? 'checked' : '')+'> '+label+'</label>';
  }
  var body = '<form id="subscriptionForm"><div class="modal-grid">'
    +formSelect('User', 'user_id', sub ? sub.user_id : (USERS[0] ? USERS[0].id : ''), userOptions)
    +formSelect('Plan', 'plan_id', sub ? (sub.plan_id || '') : '', planOptions)
    +formSelect('Status', 'status', sub ? sub.status : 'active', ['pending','active','suspended','expired','revoked'])
    +formSelect('Billing mode', 'billing_mode', sub ? sub.billing_mode : 'manual', ['manual','lifetime','periodic','trial'])
    +formInput('Starts at (ISO)', 'starts_at', sub ? (sub.starts_at || '') : '')
    +formInput('Expires at (ISO)', 'expires_at', sub ? (sub.expires_at || '') : '')
    +formInput('Device limit', 'device_limit', sub ? String(sub.device_limit || 1) : '1', {type:'number'})
    +formInput('Traffic quota bytes', 'traffic_quota_bytes', sub && sub.traffic_quota_bytes != null ? String(sub.traffic_quota_bytes) : '', {type:'number'})
    +formCheckbox('Restrict access by local time', 'access_window_enabled', !!(sub && sub.access_window_enabled), {caption:'Enable weekly local access window', full:true})
    +'<div class="mf-row full"><label class="mf-label">Days of week</label><div style=\"display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:8px;\">'
      +dayBox(0, 'Mon') + dayBox(1, 'Tue') + dayBox(2, 'Wed') + dayBox(3, 'Thu') + dayBox(4, 'Fri') + dayBox(5, 'Sat') + dayBox(6, 'Sun')
    +'</div><div class=\"mf-help\">Local time is evaluated from the device GMT offset when available, otherwise UTC.</div></div>'
    +formInput('Local start (HH:MM)', 'access_window_start_local', sub ? (sub.access_window_start_local || '') : '', {placeholder:'09:00'})
    +formInput('Local end (HH:MM)', 'access_window_end_local', sub ? (sub.access_window_end_local || '') : '', {placeholder:'18:00'})
    +'</div></form>';
  openModal(sub ? 'Edit Subscription' : 'Create Subscription', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:sub ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('subscriptionForm').requestSubmit(); }}
    ]
  });
  bindModalForm('subscriptionForm', function(fd){ saveSubscriptionForm(fd, subscriptionId); });
};

window.openTransportPackageModal = async function openTransportPackageModal(pkgId){
  var pkg = pkgId ? transportPackageById(pkgId) : null;
  var body = '<form id="transportPackageForm"><div class="modal-grid">'
    +formInput('Name', 'name', pkg ? (pkg.name || '') : '', {required:true})
    +formTextarea('Priority order', 'priority_order', pkg ? (pkg.priority_order_json || []).join(', ') : 'xray, awg, wg, openvpn_cloak', {help:'Comma-separated transport order: xray, awg, wg, openvpn_cloak'})
    +formCheckbox('Enable XRAY', 'enable_xray', pkg ? !!pkg.enable_xray : true, {caption:'Include xray profiles'})
    +formCheckbox('Enable AWG', 'enable_awg', pkg ? !!pkg.enable_awg : true, {caption:'Include AWG profiles'})
    +formCheckbox('Enable WG', 'enable_wg', pkg ? !!pkg.enable_wg : true, {caption:'Include WG profiles'})
    +formCheckbox('Enable OpenVPN+Cloak', 'enable_openvpn_cloak', pkg ? !!pkg.enable_openvpn_cloak : true, {caption:'Include OpenVPN+Cloak profiles'})
    +formCheckbox('Enable Split Tunnel', 'split_tunnel_enabled', pkg ? !!pkg.split_tunnel_enabled : false, {caption:'Apply only listed CIDRs through WG/AWG client tunnel'})
    +formTextarea('Split Tunnel Routes', 'split_tunnel_routes', pkg ? (pkg.split_tunnel_routes_json || []).join(', ') : '', {help:'Comma-separated CIDRs, for example: 10.0.0.0/8, 172.16.0.0/12'})
    +'</div></form>';
  openModal(pkgId ? 'Edit Transport Package' : 'New Transport Package', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label: pkgId ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('transportPackageForm').requestSubmit(); }}
    ]
  });
  bindModalForm('transportPackageForm', function(fd){ saveTransportPackageForm(pkgId, fd); });
};

window.deletePlanFlow = async function deletePlanFlow(planId){
  var plan = planById(planId);
  if(!confirm('Delete plan ' + (plan ? plan.code : planId) + '?')) return;
  await apiFetch(API_PREFIX + '/plans/' + encodeURIComponent(planId), { method:'DELETE' });
  await Promise.all([loadPlans(), loadSubscriptions(), loadReferralCodes()]);
};

window.deleteSubscriptionFlow = async function deleteSubscriptionFlow(subscriptionId){
  if(!confirm('Delete subscription?')) return;
  await apiFetch(API_PREFIX + '/subscriptions/' + encodeURIComponent(subscriptionId), { method:'DELETE' });
  await loadSubscriptions();
};

window.saveTransportPackageForm = async function saveTransportPackageForm(pkgId, fd){
  var routes = (fd.get('split_tunnel_routes') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var priority = (fd.get('priority_order') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var payload = {
    name: fd.get('name'),
    enable_xray: !!fd.get('enable_xray'),
    enable_awg: !!fd.get('enable_awg'),
    enable_wg: !!fd.get('enable_wg'),
    enable_openvpn_cloak: !!fd.get('enable_openvpn_cloak'),
    split_tunnel_enabled: !!fd.get('split_tunnel_enabled'),
    split_tunnel_routes: routes,
    priority_order: priority.length ? priority : ['xray', 'awg', 'wg', 'openvpn_cloak'],
  };
  if(pkgId){
    await apiFetch(API_PREFIX + '/transport-packages/' + encodeURIComponent(pkgId), {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }else{
    await apiFetch(API_PREFIX + '/transport-packages', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }
  closeModal();
  await loadTransportPackages();
};

var _userPkgShouldReconcile = false;

window.openUserPackageModal = function openUserPackageModal(userId){
  var pkg = (TRANSPORT_PACKAGES || []).find(function(p){ return p.user_id === userId; }) || null;
  var body = '<form id="userPkgForm"><div class="modal-grid">'
    +formCheckbox('Enable AWG', 'enable_awg', pkg ? !!pkg.enable_awg : true, {caption:'Include AmneziaWG profiles'})
    +formCheckbox('Enable WG', 'enable_wg', pkg ? !!pkg.enable_wg : true, {caption:'Include WireGuard profiles'})
    +formCheckbox('Enable XRAY', 'enable_xray', pkg ? !!pkg.enable_xray : true, {caption:'Include Xray profiles'})
    +formCheckbox('Enable OpenVPN+Cloak', 'enable_openvpn_cloak', pkg ? !!pkg.enable_openvpn_cloak : true, {caption:'Include OpenVPN+Cloak profiles'})
    +formCheckbox('Split Tunnel', 'split_tunnel_enabled', pkg ? !!pkg.split_tunnel_enabled : false, {caption:'Route only listed CIDRs through VPN tunnel'})
    +formInput('GeoIP Country', 'split_tunnel_country_code', pkg ? (pkg.split_tunnel_country_code || '') : '', {help:'ISO 3166-1 alpha-2 code (e.g. ru, us). Auto-computes routes for that country when saved.'})
    +formTextarea('Split Routes', 'split_tunnel_routes', pkg ? (pkg.split_tunnel_routes_json || []).join(', ') : '', {help:'Comma-separated CIDRs. Leave empty when using GeoIP Country.'})
    +formInput('Priority', 'priority_order', pkg ? (pkg.priority_order_json || []).join(', ') : 'xray, awg, wg, openvpn_cloak', {help:'Comma-separated transport priority'})
    +'</div></form>';
  openModal('User Transport Package', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Save', className:'btn', onClick:function(){ _userPkgShouldReconcile = false; document.getElementById('userPkgForm').requestSubmit(); }},
      {label:'Save & Reconcile', className:'btn pri', onClick:function(){ _userPkgShouldReconcile = true; document.getElementById('userPkgForm').requestSubmit(); }},
    ]
  });
  bindModalForm('userPkgForm', function(fd){ window.saveUserPackageForm(userId, fd, _userPkgShouldReconcile); });
};

window.saveUserPackageForm = async function saveUserPackageForm(userId, fd, reconcile){
  var pkg = (TRANSPORT_PACKAGES || []).find(function(p){ return p.user_id === userId; }) || null;
  var routes = (fd.get('split_tunnel_routes') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var priority = (fd.get('priority_order') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var payload = {
    preferred_xray_service_id: pkg ? (pkg.preferred_xray_service_id || null) : null,
    preferred_awg_service_id: pkg ? (pkg.preferred_awg_service_id || null) : null,
    preferred_wg_service_id: pkg ? (pkg.preferred_wg_service_id || null) : null,
    preferred_openvpn_cloak_service_id: pkg ? (pkg.preferred_openvpn_cloak_service_id || null) : null,
    enable_xray: !!fd.get('enable_xray'),
    enable_awg: !!fd.get('enable_awg'),
    enable_wg: !!fd.get('enable_wg'),
    enable_openvpn_cloak: !!fd.get('enable_openvpn_cloak'),
    split_tunnel_enabled: !!fd.get('split_tunnel_enabled'),
    split_tunnel_country_code: (fd.get('split_tunnel_country_code') || '').trim().toLowerCase() || null,
    split_tunnel_routes: routes,
    priority_order: priority.length ? priority : ['xray', 'awg', 'wg', 'openvpn_cloak'],
  };
  await apiFetch(API_PREFIX + '/transport-packages/by-user/' + encodeURIComponent(userId), {
    method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
  });
  if(reconcile){
    await apiFetch(API_PREFIX + '/transport-packages/by-user/' + encodeURIComponent(userId) + '/reconcile', {
      method:'POST'
    });
  }
  closeModal();
  await loadTransportPackages();
};

window.savePlanForm = async function savePlanForm(fd, planId){
  var scheduleJson = {};
  _SCHED_KEYS.forEach(function(key){
    var start = (fd.get('sched_' + key + '_start') || '').trim();
    var end   = (fd.get('sched_' + key + '_end')   || '').trim();
    if(start || end){ scheduleJson[key] = {start: start || null, end: end || null}; }
  });
  var exDates = (fd.get('access_exception_dates') || '').split(',').map(function(x){ return x.trim(); }).filter(Boolean);
  var payload = {
    name:                       fd.get('name'),
    billing_mode:               fd.get('billing_mode'),
    enabled:                    !!fd.get('enabled'),
    duration_days:              fd.get('duration_days') ? parseInt(fd.get('duration_days'), 10) : null,
    fixed_expires_at:           fd.get('fixed_expires_at') || null,
    default_device_limit:       parseInt(fd.get('default_device_limit'), 10) || 1,
    traffic_quota_bytes:        fd.get('traffic_quota_bytes') ? parseInt(fd.get('traffic_quota_bytes'), 10) : null,
    speed_limit_kbps:           fd.get('speed_limit_kbps') ? parseInt(fd.get('speed_limit_kbps'), 10) : null,
    transport_package_id:       fd.get('transport_package_id') || null,
    access_window_enabled:      !!fd.get('access_window_enabled'),
    access_schedule_json:       Object.keys(scheduleJson).length ? scheduleJson : null,
    access_exception_dates_json: exDates.length ? exDates : null,
    comment:                    fd.get('comment') || null,
  };
  if(planId){
    await apiFetch(API_PREFIX + '/plans/' + encodeURIComponent(planId), {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }else{
    payload.code = (fd.get('code') || '').trim();
    await apiFetch(API_PREFIX + '/plans', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }
  closeModal();
  await Promise.all([loadPlans(), loadReferralCodes()]);
};

window.saveSubscriptionForm = async function saveSubscriptionForm(fd, subscriptionId){
  var daysMask = 0;
  for(var i=0; i<7; i++){ if(fd.get('access_day_' + i)){ daysMask |= (1 << i); } }
  var payload = {
    user_id:                    fd.get('user_id'),
    plan_id:                    fd.get('plan_id') || null,
    status:                     fd.get('status'),
    billing_mode:               fd.get('billing_mode'),
    starts_at:                  fd.get('starts_at') || null,
    expires_at:                 fd.get('expires_at') || null,
    device_limit:               parseInt(fd.get('device_limit'), 10) || 1,
    traffic_quota_bytes:        fd.get('traffic_quota_bytes') ? parseInt(fd.get('traffic_quota_bytes'), 10) : null,
    access_window_enabled:      !!fd.get('access_window_enabled'),
    access_days_mask:           daysMask,
    access_window_start_local:  fd.get('access_window_start_local') || null,
    access_window_end_local:    fd.get('access_window_end_local') || null,
  };
  if(subscriptionId){
    await apiFetch(API_PREFIX + '/subscriptions/' + encodeURIComponent(subscriptionId), {
      method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }else{
    await apiFetch(API_PREFIX + '/subscriptions', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
    });
  }
  closeModal();
  await loadSubscriptions();
};

window.assignPoolToPlan = async function assignPoolToPlan(planId){
  var sel = document.getElementById('planPoolAssignSelect');
  var poolId = sel ? sel.value : '';
  if(!poolId) return;
  await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId), {
    method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({plan_id: planId})
  });
  closeModal();
  await Promise.all([loadPlans(), loadReferralCodes()]);
};

window.deleteTransportPackageFlow = async function deleteTransportPackageFlow(pkgId){
  var pkg = transportPackageById(pkgId);
  if(!confirm('Delete transport package ' + (pkg ? (pkg.name || pkgId) : pkgId) + '?')) return;
  try{
    await apiFetch(API_PREFIX + '/transport-packages/' + encodeURIComponent(pkgId), { method:'DELETE' });
    pushEv('transport_package.deleted', 'transport package deleted: ' + (pkg ? (pkg.name || pkgId) : pkgId));
    closeDP();
    await loadTransportPackages();
  }catch(err){
    alert(err && err.message ? err.message : err);
  }
};

export {};
