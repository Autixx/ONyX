// Page module - all functions exposed as window globals

window.loadUsers = async function loadUsers(){
  USERS = await apiFetch(API_PREFIX + '/users');
  window.renderUsers();
};

window.renderUsers = function renderUsers(){
  var tb = document.getElementById('usertb');
  if(!tb) return;
  var filterSel = document.getElementById('userSubFilter');
  var filterPlanId = filterSel ? filterSel.value : '';
  var searchEl = document.getElementById('userSearchInput');
  var searchStr = searchEl ? searchEl.value.trim().toLowerCase() : '';
  var list = USERS.filter(function(u){
    if(filterPlanId && !SUBSCRIPTIONS.some(function(s){ return s.user_id === u.id && s.plan_id === filterPlanId && s.status === 'active'; })) return false;
    if(searchStr && !(u.username||'').toLowerCase().includes(searchStr) && !(u.email||'').toLowerCase().includes(searchStr)) return false;
    return true;
  });
  if(!list.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="6">No users.</td></tr>';
    return;
  }
  tb.innerHTML = list.map(function(u){
    return '<tr>'
      +'<td class="m">'+esc(u.username)+'</td>'
      +'<td>'+esc(u.email)+'</td>'
      +'<td>'+sp(u.status)+'</td>'
      +'<td>'+esc(u.usage_goal || '-')+'</td>'
      +'<td>'+esc(String(u.requested_device_count || '-'))+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="showUser(\''+esc(u.id)+'\')">VIEW</button>'
        +'<button class="btn sm" onclick="openTransportPackageModal(\''+esc(u.id)+'\')">PACKAGE</button>'
        +'<button class="btn sm" onclick="openUserModal(\''+esc(u.id)+'\')">EDIT</button>'
        +'<button class="btn sm red" onclick="deleteUserFlow(\''+esc(u.id)+'\')">DEL</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showUser = function showUser(id){
  var u = userById(id); if(!u) return;
  openDP('User ' + u.username, rows([
    ['ID', u.id],
    ['Username', u.username],
    ['E-mail', u.email],
    ['Status', u.status],
    ['Name', ((u.first_name || '') + ' ' + (u.last_name || '')).trim() || '-'],
    ['Goal', u.usage_goal || '-'],
    ['Requested Devices', String(u.requested_device_count || '-')],
    ['Referral Code', u.referral_code || '-']
  ]), { kind:'user', id:u.id });
};

window.openUserModal = function openUserModal(userId){
  var user = userId ? userById(userId) : null;
  var body = '<form id="userForm"><div class="modal-grid">'
    +formInput('Username', 'username', user ? user.username : '', {required:true, readonly:!!user})
    +formInput('E-mail', 'email', user ? user.email : '', {required:true})
    +formInput(user ? 'New password (optional)' : 'Password', 'password', '', {type:'password', required:!user})
    +formSelect('Status', 'status', user ? user.status : 'active', ['pending','active','blocked','deleted'])
    +formInput('First name', 'first_name', user ? (user.first_name || '') : '')
    +formInput('Last name', 'last_name', user ? (user.last_name || '') : '')
    +formInput('Referral code', 'referral_code', user ? (user.referral_code || '') : '')
    +formInput('Usage goal', 'usage_goal', user ? (user.usage_goal || '') : '')
    +formInput('Requested devices', 'requested_device_count', user ? String(user.requested_device_count || 1) : '1', {type:'number', required:true})
    +'</div></form>';
  openModal(user ? 'Edit User' : 'Create User', body, {
    buttons:[
      {label:'Cancel', className:'btn', onClick:closeModal},
      {label:user ? 'Save' : 'Create', className:'btn pri', onClick:function(){ document.getElementById('userForm').requestSubmit(); }}
    ]
  });
  bindModalForm('userForm', function(fd){ saveUserForm(fd, userId); });
};

window.deleteUserFlow = async function deleteUserFlow(userId){
  var user = userById(userId);
  if(!confirm('Delete user ' + (user ? user.username : userId) + '?')) return;
  await apiFetch(API_PREFIX + '/users/' + encodeURIComponent(userId), { method:'DELETE' });
  await Promise.all([loadUsers(), loadSubscriptions(), loadDevices(), loadTransportPackages()]);
};

export {};
