// Page module - all functions exposed as window globals

window.loadReferralCodes = async function loadReferralCodes(){
  var results = await Promise.all([
    apiFetch(API_PREFIX + '/referral-codes'),
    apiFetch(API_PREFIX + '/referral-pools'),
  ]);
  REFERRAL_CODES = results[0];
  REFERRAL_POOLS = results[1];
  window.renderReferralPools();
};

window.renderReferralPools = function renderReferralPools(){
  var tb = document.getElementById('reftb');
  if(!tb) return;
  if(!REFERRAL_POOLS.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="6">No referral pools.</td></tr>';
    return;
  }
  tb.innerHTML = REFERRAL_POOLS.map(function(pool){
    var exp = pool.expires_at ? fmtDate(pool.expires_at) : '—';
    return '<tr>'
      +'<td class="m">'+esc(pool.name)+'</td>'
      +'<td>'+esc(planNameById(pool.plan_id))+'</td>'
      +'<td>'+esc(String(pool.live_codes))+'</td>'
      +'<td>'+esc(String(pool.used_codes))+'</td>'
      +'<td>'+esc(exp)+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="openEditPoolModal(\''+esc(pool.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="deletePoolFlow(\''+esc(pool.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.renderReferralCodes = function renderReferralCodes(){ window.renderReferralPools(); };

window.showReferralCode = function showReferralCode(id){
  var r = referralCodeById(id); if(!r) return;
  openDP('Referral Code ' + r.code, rows([
    ['ID', r.id],
    ['Code', r.code],
    ['Auto Approve', r.auto_approve ? 'yes' : 'no'],
    ['Plan', planNameById(r.plan_id)],
    ['Enabled', r.enabled ? 'yes' : 'no'],
    ['Used', String(r.used_count || 0)],
    ['Max Uses', r.max_uses != null ? String(r.max_uses) : '-'],
    ['Device Override', r.device_limit_override != null ? String(r.device_limit_override) : '-'],
    ['Goal Override', r.usage_goal_override || '-'],
    ['Expires', r.expires_at ? new Date(r.expires_at).toLocaleString() : '-']
  ]), { kind:'referral-code', id:r.id });
};

window.openReferralPoolModal = function openReferralPoolModal(planId){
  var planOptions = [{value:'', label:'— no subscription —'}].concat(PLANS.map(function(p){ return {value:p.id, label:p.name}; }));
  var defaultPlanId = planId || '';
  var body = '<form id="referralPoolForm"><div class="modal-grid">'
    +formInput('Pool name', 'name', '', {required:true})
    +formSelect('Subscription', 'plan_id', defaultPlanId, planOptions)
    +formCheckbox('Auto approve', 'auto_approve', false, {caption:'Approve registration automatically'})
    +formInput('Expires at (ISO)', 'expires_at', '', {help:'Leave empty for no expiry'})
    +'<div class="mf-row"><label class="mf-label">Initial codes</label>'
      +'<div style="display:flex;gap:6px;align-items:center;">'
        +'<input class="mf-input" type="number" name="code_length" value="10" min="4" max="64" style="width:72px"> length'
        +'&nbsp;&nbsp;<input class="mf-input" type="number" name="quantity" value="10" min="0" max="1000" style="width:72px"> qty'
      +'</div>'
    +'</div>'
    +'</div></form>';
  openModal('Create Referral Pool', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Create', className:'btn pri', onClick:function(){ document.getElementById('referralPoolForm').requestSubmit(); }}
    ]
  });
  bindModalForm('referralPoolForm', createReferralPool);
};

window.openEditPoolModal = async function openEditPoolModal(poolId){
  var pool = await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId));
  var planOptions = [{value:'', label:'— no subscription —'}].concat(PLANS.map(function(p){ return {value:p.id, label:p.name}; }));
  var codesHtml = '';
  if(pool.codes && pool.codes.length){
    codesHtml = '<div style="max-height:220px;overflow-y:auto;border:1px solid var(--border);border-radius:4px;padding:6px;">'
      + pool.codes.map(function(c){
        var isUsed = c.used_count > 0;
        var style = isUsed ? 'text-decoration:line-through;opacity:0.45;' : '';
        return '<div style="display:flex;align-items:center;gap:6px;padding:2px 0;">'
          +'<span class="mono" style="flex:1;font-size:12px;'+style+'">'+esc(c.code)+'</span>'
          +(isUsed ? '<span class="pill py">used</span>' : '<span class="pill pg">live</span>')
          +(!isUsed ? '<button class="btn sm" onclick="navigator.clipboard.writeText(\''+esc(c.code)+'\').catch(function(){})">COPY</button>' : '')
          +(!isUsed ? '<button class="btn sm red" onclick="deletePoolCodeFlow(\''+esc(poolId)+'\',\''+esc(c.id)+'\')">DEL</button>' : '')
        +'</div>';
      }).join('')
      +'</div>';
  } else {
    codesHtml = '<div class="muted" style="font-size:12px;padding:4px">No codes in this pool.</div>';
  }
  var hasLive = pool.live_codes > 0;
  var hasUsed = pool.used_codes > 0;
  var body = '<form id="editPoolSettingsForm"><div class="modal-grid">'
    +formInput('Pool name', 'name', pool.name, {required:true})
    +formSelect('Subscription', 'plan_id', pool.plan_id || '', planOptions)
    +formCheckbox('Auto approve', 'auto_approve', pool.auto_approve, {caption:'Approve registration automatically'})
    +formInput('Expires at (ISO)', 'expires_at', pool.expires_at || '')
    +'</div></form>'
    +'<div style="margin-top:16px">'
      +'<div class="stitle" style="font-size:12px;margin-bottom:6px">Codes — '
        +esc(String(pool.total_codes))+' total, <span style="color:var(--ok)">'+esc(String(pool.live_codes))+' live</span>, '
        +esc(String(pool.used_codes))+' used'
      +'</div>'
      +codesHtml
    +'</div>'
    +'<div style="margin-top:12px;display:flex;gap:6px;align-items:center;flex-wrap:wrap;">'
      +'<input class="mf-input" type="number" id="genMoreLength" value="10" min="4" max="64" style="width:72px"> length'
      +'&nbsp;&nbsp;<input class="mf-input" type="number" id="genMoreQty" value="10" min="1" max="1000" style="width:72px"> qty'
      +'<button class="btn sm pri" onclick="generateMorePoolCodes(\''+esc(poolId)+'\')">GENERATE MORE</button>'
    +'</div>'
    +(!hasLive && hasUsed ? '<div style="margin-top:10px"><button class="btn sm red" onclick="forceDeletePool(\''+esc(poolId)+'\')">DELETE POOL (with used codes)</button></div>' : '');
  openModal('Pool: ' + esc(pool.name), body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Save', className:'btn pri', onClick:function(){ document.getElementById('editPoolSettingsForm').requestSubmit(); }}
    ]
  });
  bindModalForm('editPoolSettingsForm', function(fd){ savePoolForm(fd, poolId); });
};

window.deletePoolCodeFlow = async function deletePoolCodeFlow(poolId, codeId){
  if(!confirm('Delete this code?')) return;
  await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId) + '/codes/' + encodeURIComponent(codeId), { method:'DELETE' });
  window.openEditPoolModal(poolId);
};

window.deletePoolFlow = async function deletePoolFlow(poolId){
  var pool = REFERRAL_POOLS.find(function(p){ return p.id === poolId; });
  var name = pool ? pool.name : poolId;
  if(!confirm('Delete pool "' + name + '"?')) return;
  try {
    var result = await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId), { method:'DELETE' });
    if(result && !result.deleted_pool){
      alert(String(result.deleted_codes) + ' unused code(s) deleted. Pool has used codes and was kept.');
    }
    await loadReferralCodes();
  } catch(err){
    if(err.message && err.message.indexOf('live') !== -1){
      if(confirm('Pool has live (unused) codes.\n\nDelete unused codes only and keep the pool?')){
        var r2 = await apiFetch(API_PREFIX + '/referral-pools/' + encodeURIComponent(poolId) + '?force=true', { method:'DELETE' });
        if(r2) alert(String(r2.deleted_codes) + ' unused code(s) deleted. Pool kept.');
        await loadReferralCodes();
      }
    } else {
      alert('Error: ' + err.message);
    }
  }
};

window.openReferralCodeModal = function openReferralCodeModal(referralId){
  var ref = referralId ? referralCodeById(referralId) : null;
  var planOptions = [{value:'', label:'-'}].concat(PLANS.map(function(p){ return {value:p.id, label:p.name}; }));
  var body = '<form id="referralCodeForm"><div class="modal-grid">'
    +formInput('Code', 'code', ref ? ref.code : '', {required:true, readonly:!!ref})
    +formSelect('Plan', 'plan_id', ref ? (ref.plan_id || '') : '', planOptions)
    +formCheckbox('Enabled', 'enabled', ref ? ref.enabled : true, {caption:'Code enabled'})
    +formCheckbox('Auto approve', 'auto_approve', ref ? ref.auto_approve : false, {caption:'Approve registration automatically'})
    +formInput('Max uses', 'max_uses', ref && ref.max_uses != null ? String(ref.max_uses) : '', {type:'number'})
    +formInput('Device limit override', 'device_limit_override', ref && ref.device_limit_override != null ? String(ref.device_limit_override) : '', {type:'number'})
    +formInput('Usage goal override', 'usage_goal_override', ref ? (ref.usage_goal_override || '') : '')
    +formInput('Expires at (ISO)', 'expires_at', ref ? (ref.expires_at || '') : '')
    +formTextarea('Note', 'note', ref ? (ref.note || '') : '', {full:true})
    +'</div></form>';
  openModal(ref ? 'Edit Referral Code' : 'Create Referral Code', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:ref ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('referralCodeForm').requestSubmit(); }}
    ]
  });
  bindModalForm('referralCodeForm', function(fd){ saveReferralCodeForm(fd, referralId); });
};

window.deleteReferralCodeFlow = async function deleteReferralCodeFlow(referralId){
  var ref = referralCodeById(referralId);
  if(!confirm('Delete referral code ' + (ref ? ref.code : referralId) + '?')) return;
  await apiFetch(API_PREFIX + '/referral-codes/' + encodeURIComponent(referralId), { method:'DELETE' });
  await loadReferralCodes();
};

export {};
