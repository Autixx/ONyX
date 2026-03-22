// Page module - all functions exposed as window globals

window.REGISTRATIONS = [];

window.loadRegistrations = async function loadRegistrations(){
  try{
    var data = await apiFetch(API_PREFIX + '/registrations');
    window.REGISTRATIONS = Array.isArray(data) ? data : (data && data.items ? data.items : []);
  }catch(e){
    // endpoint may not exist yet — keep current list or show empty
    if(!window.REGISTRATIONS.length){ window.REGISTRATIONS = []; }
  }
  window.renderRegistrations();
  window.updateRegBadge();
};

window.updateRegBadge = function updateRegBadge(){
  var badge = document.getElementById('regBadge');
  if(!badge) return;
  var pending = window.REGISTRATIONS.filter(function(r){ return r.status === 'pending'; }).length;
  if(pending > 0){
    badge.textContent = String(pending);
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }
};

window.renderRegistrations = function renderRegistrations(){
  var tb = document.getElementById('regtb');
  if(!tb) return;
  var filter = '';
  var sel = document.getElementById('regStatusFilter');
  if(sel) filter = sel.value;
  var rows = window.REGISTRATIONS.filter(function(r){
    return !filter || r.status === filter;
  });
  if(!rows.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="7">'+t('reg.empty')+'</td></tr>';
    return;
  }
  tb.innerHTML = rows.map(function(r){
    var statusCls = r.status === 'pending' ? 'pa' : r.status === 'approved' ? 'pg' : 'pr';
    var rowCls = r.status === 'pending' ? 'reg-row-pending' : r.status === 'rejected' ? 'reg-row-rejected' : '';
    var actions = '';
    if(r.status === 'pending'){
      actions = '<button class="btn sm pri" onclick="approveReg(\''+esc(r.id)+'\')">'+t('reg.approve')+'</button>'
               +'<button class="btn sm red" onclick="rejectReg(\''+esc(r.id)+'\')">'+t('reg.reject')+'</button>';
    }
    return '<tr class="'+rowCls+'">'
      +'<td class="m">'+esc(r.username || r.login || '-')+'</td>'
      +'<td>'+esc(r.email || '-')+'</td>'
      +'<td style="color:var(--t1);font-size:13px;">'+esc(r.created_at ? new Date(r.created_at).toLocaleString() : (r.date || '-'))+'</td>'
      +'<td class="m">'+esc(r.referral_code || r.ref_code || '-')+'</td>'
      +'<td style="text-align:center;">'+esc(String(r.device_count != null ? r.device_count : (r.devices != null ? r.devices : '-')))+'</td>'
      +'<td><span class="pill '+statusCls+'">'+esc(r.status)+'</span></td>'
      +'<td><div class="reg-actions">'+actions+'</div></td>'
      +'</tr>';
  }).join('');
};

export {};
