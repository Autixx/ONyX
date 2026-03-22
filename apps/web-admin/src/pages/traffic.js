// Page module - all functions exposed as window globals

window.nodeTrafficState = function nodeTrafficState(item){
  if(item.traffic_hard_enforced_at) return 'hard-enforced';
  if(item.traffic_suspended_at) return 'suspended';
  if(item.usage_ratio == null) return 'normal';
  if(item.usage_ratio >= 1.0) return 'exceeded';
  if(item.usage_ratio >= 0.8) return 'warning';
  return 'normal';
};

window.renderNodeTraffic = function renderNodeTraffic(){
  var tb = document.getElementById('ttb');
  if(!tb) return;
  var filters = getNodeTrafficFilters();
  var rows = NODE_TRAFFIC.filter(function(item){
    var state = nodeTrafficState(item);
    if(filters.state && state !== filters.state) return false;
    if(filters.search){
      var hay = [
        item.node_name,
        item.node_status,
        item.traffic_suspension_reason
      ].join(' ').toLowerCase();
      if(hay.indexOf(filters.search) === -1) return false;
    }
    return true;
  });
  if(!rows.length){
    tb.innerHTML = '<tr><td class="empty-state" colspan="10">No node traffic entries match the current filter.</td></tr>';
    return;
  }
  tb.innerHTML = rows.map(function(item){
    var state = nodeTrafficState(item);
    var usedCls = state === 'exceeded' || state === 'suspended' || state === 'hard-enforced' ? 'traffic-crit' : state === 'warning' ? 'traffic-warn' : '';
    var ratioText = item.usage_ratio != null ? (Math.round(item.usage_ratio * 1000) / 10) + '%' : '-';
    return '<tr onclick="showNodeTraffic(\''+esc(item.node_id)+'\')">'
      +'<td class="m">'+esc(item.node_name)+'</td>'
      +'<td>'+sp(item.node_status)+'</td>'
      +'<td style="color:var(--t1)">'+fmtDate(item.cycle_started_at)+'</td>'
      +'<td style="color:var(--t1)">'+fmtDate(item.cycle_ends_at)+'</td>'
      +'<td class="'+usedCls+'">'+esc(String(item.traffic_used_gb))+' GB</td>'
      +'<td style="color:var(--t1)">'+(item.traffic_limit_gb != null ? esc(String(item.traffic_limit_gb)) + ' GB' : '—')+'</td>'
      +'<td class="'+usedCls+'">'+esc(ratioText)+'</td>'
      +'<td>'+(item.traffic_suspended_at ? '<span class="pill pr">suspended</span>' : '<span class="pill pg">no</span>')+'</td>'
      +'<td>'+(item.traffic_hard_enforced_at ? '<span class="pill pr">yes</span>' : '<span class="pill pg">no</span>')+'</td>'
      +'<td style="display:flex;gap:5px;">'
        +'<button class="btn sm" onclick="event.stopPropagation();showNodeTraffic(\''+esc(item.node_id)+'\')">VIEW</button>'
        +'<button class="btn sm" onclick="event.stopPropagation();actionNodeTrafficReset(\''+esc(item.node_id)+'\')">RESET</button>'
        +'<button class="btn sm red" onclick="event.stopPropagation();actionNodeTrafficRollover(\''+esc(item.node_id)+'\')">ROLLOVER</button>'
      +'</td>'
      +'</tr>';
  }).join('');
};

window.showNodeTraffic = async function showNodeTraffic(nodeId){
  try{
    var overview = await apiFetch(API_PREFIX + '/node-traffic/nodes/' + encodeURIComponent(nodeId));
    var current = overview.current_cycle;
    var ratio = current && current.usage_ratio != null ? (Math.round(current.usage_ratio * 1000) / 10) + '%' : '-';
    var recent = (overview.recent_cycles || []).slice(0, 6).map(function(cycle){
      return '<div class="drow"><span class="dk">'+esc(fmtDate(cycle.cycle_started_at))+'</span><span class="dv">'+esc(String(cycle.used_gb)+' GB')+'</span></div>';
    }).join('');
    openDP((overview.node_name || nodeId) + ' — Traffic',
      rows([
        ['Cycle Start', current ? fmtDate(current.cycle_started_at) : '-'],
        ['Cycle End', current ? fmtDate(current.cycle_ends_at) : '-'],
        ['Used', current ? String(current.used_gb) + ' GB' : '-'],
        ['Limit', current && current.traffic_limit_gb != null ? String(current.traffic_limit_gb) + ' GB' : '-'],
        ['Usage Ratio', ratio],
        ['Suspended', overview.traffic_suspended_at ? 'yes' : 'no'],
        ['Suspension Reason', overview.traffic_suspension_reason || '-'],
        ['Hard Enforced', overview.traffic_hard_enforced_at ? 'yes' : 'no'],
        ['Hard Enforcement Reason', overview.traffic_hard_enforcement_reason || '-'],
        ['Warning Triggered', current && current.warning_emitted_at ? fmtDate(current.warning_emitted_at) : '-'],
        ['Exceeded Triggered', current && current.exceeded_emitted_at ? fmtDate(current.exceeded_emitted_at) : '-']
      ])
      + '<div style="margin-top:10px;color:var(--t2);font-size:12px;text-transform:uppercase;letter-spacing:.12em;">Recent Cycles</div>'
      + '<div style="margin-top:8px;">' + (recent || '<div class="drow"><span class="dk">No data</span><span class="dv">-</span></div>') + '</div>'
      + '<div id="nodeTrafficEventsBox" style="margin-top:14px;color:var(--t1);font-size:13px;">Loading traffic events…</div>'
      + '<div class="dp-actions">'
        +'<button class="btn" onclick="actionNodeTrafficReset(\''+esc(nodeId)+'\')">RESET</button>'
        +'<button class="btn red" onclick="actionNodeTrafficRollover(\''+esc(nodeId)+'\')">ROLLOVER</button>'
      +'</div>',
      { kind:'node-traffic', id:nodeId }
    );
    loadNodeTrafficEvents(nodeId, 'nodeTrafficEventsBox');
  }catch(e){
    pushEv('node.traffic.error', String(e && e.message ? e.message : e));
    alert(e&&e.message?e.message:e);
  }
};

window.refreshNodeTrafficSummary = async function refreshNodeTrafficSummary(){
  var items = await apiFetch(API_PREFIX + '/node-traffic/summary');
  NODE_TRAFFIC = Array.isArray(items) ? items : [];
  renderNodeTraffic();
};

window.actionNodeTrafficReset = async function actionNodeTrafficReset(nodeId){
  if(!confirm('Reset current traffic cycle counters for this node?')) return;
  try{
    var result = await apiFetch(API_PREFIX + '/node-traffic/nodes/' + encodeURIComponent(nodeId) + '/reset', { method:'POST', body:{} });
    pushEv('node.traffic.reset', 'traffic reset for ' + (result.node_name || nodeId));
    await refreshNodes();
    await refreshNodeTrafficSummary();
    await refreshTopology();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('node-traffic', nodeId)){ showNodeTraffic(nodeId); }
  }catch(err){
    pushEv('node.traffic.reset.error', 'traffic reset failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionNodeTrafficRollover = async function actionNodeTrafficRollover(nodeId){
  if(!confirm('Rollover the current traffic cycle and start a new one now?')) return;
  try{
    var result = await apiFetch(API_PREFIX + '/node-traffic/nodes/' + encodeURIComponent(nodeId) + '/rollover', { method:'POST', body:{} });
    pushEv('node.traffic.rollover', 'traffic cycle rolled over for ' + (result.node_name || nodeId));
    await refreshNodes();
    await refreshNodeTrafficSummary();
    await refreshTopology();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('node-traffic', nodeId)){ showNodeTraffic(nodeId); }
  }catch(err){
    pushEv('node.traffic.rollover.error', 'traffic rollover failed for ' + nodeId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.loadNodeTrafficEvents = async function loadNodeTrafficEvents(nodeId, containerId){
  var box = document.getElementById(containerId);
  if(!box) return;
  try{
    var items = await apiFetch(API_PREFIX + '/audit-logs?limit=8&entity_type=node_traffic&entity_id=' + encodeURIComponent(nodeId));
    var html = '<div style="margin-top:10px;color:var(--t2);font-size:12px;text-transform:uppercase;letter-spacing:.12em;">Recent Traffic Events</div>';
    if(!items || !items.length){
      box.innerHTML = html + '<div class="drow"><span class="dk">No events</span><span class="dv">-</span></div>';
      return;
    }
    html += '<div style="margin-top:8px;">' + items.slice(0, 6).map(function(evt){
      return '<div class="drow"><span class="dk">'+esc(fmtDate(evt.created_at))+'</span><span class="dv">'+esc(evt.message || evt.level || '-')+'</span></div>';
    }).join('') + '</div>';
    box.innerHTML = html;
  }catch(_){
    box.innerHTML = '<div style="color:var(--rd)">Failed to load traffic events.</div>';
  }
};

export {};
