// Page module - all functions exposed as window globals

window.loadPeers = async function loadPeers(){
  try{
    var data = await apiFetch(API_PREFIX + '/peers');
    PEERS = Array.isArray(data) ? data : (data && data.items ? data.items : []);
  }catch(e){
    if(!PEERS.length) PEERS = [];
  }
  renderPeers();
  updatePeersBadge();
  renderXrayServices();
  renderAwgServices();
  renderWgServices();
  renderOpenvpnCloakServices();
};

window.renderPeers = function renderPeers(){
  var tb = document.getElementById('peerstb');
  if(!tb) return;

  // Populate node filter
  var nodeFilter = document.getElementById('peerNodeFilter');
  if(nodeFilter && nodeFilter.options.length <= 1){
    NODES.forEach(function(n){
      var opt = document.createElement('option');
      opt.value = n.id; opt.textContent = n.name;
      nodeFilter.appendChild(opt);
    });
  }

  var search = (document.getElementById('peerSearch')||{}).value || '';
  var nodeId = (document.getElementById('peerNodeFilter')||{}).value || '';
  search = search.trim().toLowerCase();

  var rows = PEERS.filter(function(p){
    if(nodeId && p.node_id !== nodeId) return false;
    if(search){
      var hay = [p.username,p.email,p.last_ip,p.node_id].join(' ').toLowerCase();
      if(hay.indexOf(search) === -1) return false;
    }
    return true;
  });

  if(!rows.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="9">No peers found.</td></tr>';
    return;
  }

  tb.innerHTML = rows.map(function(p){
    var node = NODES.find(function(n){ return n.id === p.node_id; });
    var nodeName = node ? node.name : (p.node_id || '-');
    var expired = isExpired(p.config_expires_at);
    var expClass = expired ? 'style="color:var(--red)"' : '';
    return '<tr onclick="showPeerDetail(\''+esc(p.id)+'\')" style="cursor:pointer">'
      +'<td class="m">'+esc(p.username||'-')+'</td>'
      +'<td style="color:var(--t1)">'+esc(p.email||'-')+'</td>'
      +'<td><span class="pill pb">'+esc(nodeName)+'</span></td>'
      +'<td style="color:var(--t1);font-size:13px;">'+fmtDate(p.registered_at)+'</td>'
      +'<td '+expClass+'>'+fmtDate(p.config_expires_at)+(expired?' <span class="pill pr">expired</span>':'')+'</td>'
      +'<td class="m">'+esc(p.last_ip||'-')+'</td>'
      +'<td style="color:var(--t1)">'+fmtBytes(p.traffic_24h_mb)+'</td>'
      +'<td style="color:var(--t1)">'+fmtBytes(p.traffic_month_mb)+'</td>'
      +'<td><div style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();openPeerConfig(\''+esc(p.id)+'\')">CONFIG</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();revokePeer(\''+esc(p.id)+'\')">REVOKE</button>'
      +'</div></td>'
      +'</tr>';
  }).join('');
};

window.updatePeersBadge = function updatePeersBadge(){
  var badge = document.getElementById('peersBadge');
  if(!badge) return;
  badge.textContent = String(PEERS.length);
  if(PEERS.length > 0){ badge.style.display = ''; }
  else { badge.style.display = 'none'; }
};

window.showPeerDetail = function showPeerDetail(id){
  var p = PEERS.find(function(x){ return x.id===id; });
  if(!p) return;
  var node = NODES.find(function(n){ return n.id === p.node_id; });
  var user = USERS.find(function(u){ return u.email === p.email; });
  var sub = user ? SUBSCRIPTIONS.find(function(s){ return s.user_id === user.id && s.status === 'active'; }) : null;
  var pkg = user ? TRANSPORT_PACKAGES.find(function(t){ return t.user_id === user.id; }) : null;
  openDP(p.username || 'Peer',
    rows([
      ['ID', p.id],
      ['Login', p.username||'-'],
      ['E-mail', p.email||'-'],
      ['Node', node ? node.name : (p.node_id||'-')],
      ['Subscription', sub ? planNameById(sub.plan_id) + ' (' + sub.status + ')' : '-'],
      ['Transport Pkg', pkg ? (pkg.name || pkg.id) : '-'],
      ['Registered', fmtDate(p.registered_at)],
      ['Config Expires', fmtDate(p.config_expires_at)],
      ['Last IP', p.last_ip||'-'],
      ['Traffic 24h', fmtBytes(p.traffic_24h_mb)],
      ['Traffic Month', fmtBytes(p.traffic_month_mb)],
    ])
    +'<div class="dp-actions">'
      +'<button class="btn pri" onclick="openPeerConfig(\''+esc(p.id)+'\')">VIEW CONFIG</button>'
      +'<button class="btn red" onclick="revokePeer(\''+esc(p.id)+'\')">REVOKE</button>'
    +'</div>'
  );
};

export {};
