// Page module - all functions exposed as window globals

window.loadDevices = async function loadDevices(){
  DEVICES = await apiFetch(API_PREFIX + '/devices');
  window.renderDevices();
};

window.renderDevices = function renderDevices(){
  var tb = document.getElementById('devtb');
  if(!tb) return;
  if(!DEVICES.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="7">No devices.</td></tr>';
    return;
  }
  tb.innerHTML = DEVICES.map(function(d){
    var osPart = d.os_version ? (' / ' + d.os_version) : '';
    return '<tr>'
      +'<td class="m">'+esc(d.user_username || userNameById(d.user_id))+'</td>'
      +'<td>'+esc(d.device_label || '-')+'</td>'
      +'<td>'+esc((d.platform || '-') + osPart)+'</td>'
      +'<td>'+esc(d.timezone_gmt || '-')+'</td>'
      +'<td>'+sp(d.status)+'</td>'
      +'<td>'+esc(d.verified_at ? new Date(d.verified_at).toLocaleString() : '-')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="showDevice(\''+esc(d.id)+'\')">VIEW</button>'
        +(d.status !== 'banned' ? '<button class="btn sm" onclick="openDeviceBanModal(\''+esc(d.id)+'\')">BAN</button>' : '<button class="btn sm" onclick="unbanDeviceFlow(\''+esc(d.id)+'\')">UNBAN</button>')
        +'<button class="btn sm red" onclick="revokeDeviceFlow(\''+esc(d.id)+'\')">REVOKE</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showDevice = function showDevice(id){
  var d = deviceById(id); if(!d) return;
  openDP('Device ' + (d.device_label || d.id), rows([
    ['ID', d.id],
    ['User', d.user_username || userNameById(d.user_id)],
    ['Label', d.device_label || '-'],
    ['Platform', d.platform || '-'],
    ['OS Version', d.os_version || '-'],
    ['GMT', d.timezone_gmt || '-'],
    ['App Version', d.app_version || '-'],
    ['Status', d.status],
    ['Ban Reason', d.ban_reason || '-'],
    ['Banned Until', d.banned_until ? new Date(d.banned_until).toLocaleString() : (d.status === 'banned' ? 'permanent' : '-')],
    ['Verified', d.verified_at ? new Date(d.verified_at).toLocaleString() : '-'],
    ['Created', d.created_at ? new Date(d.created_at).toLocaleString() : '-']
  ])
  +'<div class="dp-actions">'
    +(d.status === 'banned'
      ? '<button class="btn" onclick="unbanDeviceFlow(\''+esc(d.id)+'\')">UNBAN</button>'
      : '<button class="btn" onclick="openDeviceBanModal(\''+esc(d.id)+'\')">BAN</button>')
    +'<button class="btn red" onclick="revokeDeviceFlow(\''+esc(d.id)+'\')">REVOKE</button>'
  +'</div>', { kind:'device', id:d.id });
};

window.openDeviceBanModal = function openDeviceBanModal(deviceId){
  var device = deviceById(deviceId); if(!device) return;
  var body = '<form id="deviceBanForm"><div class="modal-grid">'
    +formCheckbox('Permanent ban', 'permanent', false, {caption:'Keep the device banned until manually unbanned'})
    +formInput('Duration', 'duration_value', '30', {type:'number', required:true})
    +formSelect('Unit', 'duration_unit', 'minutes', [
      {value:'minutes', label:'minutes'},
      {value:'hours', label:'hours'},
      {value:'days', label:'days'}
    ])
    +formTextarea('Reason', 'reason', '', {full:true})
    +'</div></form>';
  openModal('Ban Device — ' + (device.device_label || device.id), body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:'Ban', className:'btn pri', onClick:function(){ document.getElementById('deviceBanForm').requestSubmit(); }}
    ]
  });
  var permanentBox = document.querySelector('#deviceBanForm input[name="permanent"]');
  var durationInput = document.getElementById('duration_value');
  var durationUnit = document.getElementById('duration_unit');
  function syncBanFields(){
    var disabled = !!(permanentBox && permanentBox.checked);
    if(durationInput){ durationInput.disabled = disabled; }
    if(durationUnit){ durationUnit.disabled = disabled; }
  }
  if(permanentBox){ permanentBox.addEventListener('change', syncBanFields); }
  syncBanFields();
  bindModalForm('deviceBanForm', function(fd){ saveDeviceBanForm(deviceId, fd); });
};

window.revokeDeviceFlow = async function revokeDeviceFlow(deviceId){
  var d = deviceById(deviceId);
  var label = d ? (d.device_label || d.id) : deviceId;
  if(!confirm('Revoke device "' + label + '"? It will no longer be able to connect.')) return;
  await apiFetch(API_PREFIX + '/devices/' + encodeURIComponent(deviceId) + '/revoke', { method:'POST' });
  closeDP();
  await loadDevices();
};

window.unbanDeviceFlow = async function unbanDeviceFlow(deviceId){
  var d = deviceById(deviceId);
  var label = d ? (d.device_label || d.id) : deviceId;
  if(!confirm('Unban device "' + label + '"?')) return;
  await apiFetch(API_PREFIX + '/devices/' + encodeURIComponent(deviceId) + '/unban', { method:'POST' });
  closeDP();
  await loadDevices();
};

window.saveDeviceBanForm = async function saveDeviceBanForm(deviceId, fd){
  var permanent = !!fd.get('permanent');
  var payload = { permanent: permanent, reason: fd.get('reason') || null };
  if(!permanent){
    var val = parseInt(fd.get('duration_value'), 10) || 30;
    var unit = fd.get('duration_unit') || 'minutes';
    var multiplier = unit === 'days' ? 1440 : unit === 'hours' ? 60 : 1;
    payload.duration_minutes = val * multiplier;
  }
  await apiFetch(API_PREFIX + '/devices/' + encodeURIComponent(deviceId) + '/ban', {
    method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)
  });
  closeModal();
  await loadDevices();
};

export {};
