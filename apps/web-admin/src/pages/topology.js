// Page module - all functions exposed as window globals

window.TOPO_AUTO_REFRESH_ENABLED = true;
window.TOPO_ZOOM = 1.0;
window.TOPO_ZOOM_MIN = 0.35;
window.TOPO_ZOOM_MAX = 2.5;
window.TOPO_PAN_X = 0;
window.TOPO_PAN_Y = 0;
window._topologyAutoTimer = null;
window._topologyAutoInFlight = false;
window._topologyRealtimeTimer = null;
window._topologyMetaTimer = null;

window._topologyPosSaveTimer = null;

window.scheduleTopologyPosSave = function scheduleTopologyPosSave(pos){
  if(window._topologyPosSaveTimer) clearTimeout(window._topologyPosSaveTimer);
  window._topologyPosSaveTimer = setTimeout(function(){
    window._topologyPosSaveTimer = null;
    apiFetch(API_PREFIX + '/graph/positions', {method:'PUT', body:{positions: pos}}).catch(function(){});
  }, 600);
};

window.refreshTopology = async function refreshTopology(){
  var graph = await apiFetch(API_PREFIX + '/graph');
  GRAPH_DATA = graph || {nodes:[], edges:[], generated_at:null};
  var svg = document.getElementById('tc');
  if(svg && !svg._nodePos){
    try{
      var posData = await apiFetch(API_PREFIX + '/graph/positions');
      if(posData && posData.positions && Object.keys(posData.positions).length){
        svg._nodePos = {};
        Object.keys(posData.positions).forEach(function(id){
          var p = posData.positions[id];
          svg._nodePos[id] = {x: Number(p.x || 0), y: Number(p.y || 0)};
        });
      }
    }catch(_){}
  }
  renderTopologyMeta();
  drawTopo();
};

window.scheduleTopologyRealtimeRefresh = function scheduleTopologyRealtimeRefresh(){
  if(window.CURRENT_PAGE !== 'topology') return;
  if(_topologyRealtimeTimer) return;
  _topologyRealtimeTimer = setTimeout(function(){
    _topologyRealtimeTimer = null;
    refreshTopology().catch(function(){});
  }, 250);
};

window.syncTopologyAutoButton = function syncTopologyAutoButton(){
  var btn = document.getElementById('btnTopoAuto');
  if(!btn) return;
  btn.classList.toggle('pri', !!TOPO_AUTO_REFRESH_ENABLED);
  btn.setAttribute('aria-pressed', TOPO_AUTO_REFRESH_ENABLED ? 'true' : 'false');
};

window.topologyAutoRefreshTick = async function topologyAutoRefreshTick(){
  if(!TOPO_AUTO_REFRESH_ENABLED) return;
  if(window.CURRENT_PAGE !== 'topology') return;
  if(_topologyAutoInFlight) return;
  _topologyAutoInFlight = true;
  try{
    await refreshTopology();
  }catch(err){
    console.warn('topology auto refresh failed', err);
  }finally{
    _topologyAutoInFlight = false;
  }
};

window.stopTopologyAutoRefresh = function stopTopologyAutoRefresh(){
  if(_topologyAutoTimer){
    clearInterval(_topologyAutoTimer);
    _topologyAutoTimer = null;
  }
};

window.stopTopologyMetaRefresh = function stopTopologyMetaRefresh(){
  if(_topologyMetaTimer){
    clearInterval(_topologyMetaTimer);
    _topologyMetaTimer = null;
  }
};

window.startTopologyMetaRefresh = function startTopologyMetaRefresh(){
  stopTopologyMetaRefresh();
  if(window.CURRENT_PAGE !== 'topology') return;
  _topologyMetaTimer = setInterval(function(){
    renderTopologyMeta();
  }, 1000);
};

window.startTopologyAutoRefresh = function startTopologyAutoRefresh(){
  stopTopologyAutoRefresh();
  if(!TOPO_AUTO_REFRESH_ENABLED) return;
  if(window.CURRENT_PAGE !== 'topology') return;
  _topologyAutoTimer = setInterval(function(){
    topologyAutoRefreshTick();
  }, 5000);
};

window.toggleTopologyAutoRefresh = function toggleTopologyAutoRefresh(){
  TOPO_AUTO_REFRESH_ENABLED = !TOPO_AUTO_REFRESH_ENABLED;
  syncTopologyAutoButton();
  if(TOPO_AUTO_REFRESH_ENABLED){
    topologyAutoRefreshTick();
    startTopologyAutoRefresh();
  } else {
    stopTopologyAutoRefresh();
  }
};

window.fmtRelativeAge = function fmtRelativeAge(value){
  if(!value) return '-';
  var d = new Date(value);
  if(isNaN(d.getTime())) return String(value);
  var seconds = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if(seconds < 60) return seconds + 's ago';
  var minutes = Math.floor(seconds / 60);
  if(minutes < 60) return minutes + 'm ago';
  var hours = Math.floor(minutes / 60);
  if(hours < 24) return hours + 'h ago';
  return Math.floor(hours / 24) + 'd ago';
};

window.clampTopologyZoom = function clampTopologyZoom(value){
  return Math.max(TOPO_ZOOM_MIN, Math.min(TOPO_ZOOM_MAX, value));
};

window.syncTopologyZoomLabel = function syncTopologyZoomLabel(){
  var label = document.getElementById('topoZoomLabel');
  if(!label) return;
  label.textContent = 'ZOOM ' + Math.round(clampTopologyZoom(TOPO_ZOOM) * 100) + '%';
};

window.adjustTopologyZoom = function adjustTopologyZoom(factor){
  TOPO_ZOOM = clampTopologyZoom((TOPO_ZOOM || 1) * factor);
  applyTopologyZoom(document.getElementById('tc'));
};

window.resetTopologyView = function resetTopologyView(){
  TOPO_ZOOM = 1.0;
  TOPO_PAN_X = 0;
  TOPO_PAN_Y = 0;
  applyTopologyZoom(document.getElementById('tc'));
};

window.applyTopologyZoom = function applyTopologyZoom(svg){
  if(!svg || !svg._topoWorld) return;
  var W = svg._viewWidth || (svg.getBoundingClientRect().width || 900);
  var H = svg._viewHeight || 480;
  var s = clampTopologyZoom(TOPO_ZOOM);
  TOPO_ZOOM = s;
  var cx = W / 2;
  var cy = H / 2;
  svg._topoWorld.setAttribute('transform', 'translate(' + (cx + TOPO_PAN_X) + ' ' + (cy + TOPO_PAN_Y) + ') scale(' + s + ') translate(' + (-cx) + ' ' + (-cy) + ')');
  syncTopologyZoomLabel();
};

window.bindTopologyZoom = function bindTopologyZoom(svg){
  if(!svg || svg._zoomBound) return;
  svg.addEventListener('wheel', function(event){
    event.preventDefault();
    var factor = event.deltaY < 0 ? 1.1 : 0.9;
    var oldZoom = clampTopologyZoom(TOPO_ZOOM);
    var newZoom = clampTopologyZoom(oldZoom * factor);
    if(oldZoom === newZoom) return;

    // Cursor position relative to SVG element
    var rect = svg.getBoundingClientRect();
    var mx = event.clientX - rect.left;
    var my = event.clientY - rect.top;

    // Canvas centre (origin of the transform)
    var W = svg._viewWidth || rect.width || 900;
    var H = svg._viewHeight || rect.height || 480;
    var cx = W / 2;
    var cy = H / 2;

    // World point currently under the cursor:
    //   screen→world: w = (m - cx - PAN) / oldZoom + cx
    var wx = (mx - cx - TOPO_PAN_X) / oldZoom + cx;
    var wy = (my - cy - TOPO_PAN_Y) / oldZoom + cy;

    // Adjust pan so that same world point stays under cursor after zoom:
    //   PAN_new = m - cx - (w - cx) * newZoom
    TOPO_PAN_X = mx - cx - (wx - cx) * newZoom;
    TOPO_PAN_Y = my - cy - (wy - cy) * newZoom;
    TOPO_ZOOM  = newZoom;

    applyTopologyZoom(svg);
  }, { passive:false });
  svg._zoomBound = true;
};

window.renderTopologyMeta = function renderTopologyMeta(){
  var summary = document.getElementById('topoSummary');
  var pathSummary = document.getElementById('topoPathSummary');
  if(summary){
    var nodes = GRAPH_DATA.nodes || [];
    var edges = GRAPH_DATA.edges || [];
    var activeEdges = edges.filter(function(edge){ return edge.state === 'active'; }).length;
    var degradedNodes = nodes.filter(function(node){ return node.status === 'degraded'; }).length;
    var offlineNodes = nodes.filter(function(node){ return node.status === 'offline' || node.status === 'unreachable'; }).length;
    summary.innerHTML = rows([
      ['Generated', GRAPH_DATA.generated_at ? (fmtDateTime(GRAPH_DATA.generated_at) + ' (' + fmtRelativeAge(GRAPH_DATA.generated_at) + ')') : '-'],
      ['Nodes', String(nodes.length)],
      ['Links', String(edges.length)],
      ['Active Links', String(activeEdges)],
      ['Degraded Nodes', String(degradedNodes)],
      ['Offline Nodes', String(offlineNodes)]
    ]);
  }
  if(pathSummary){
    if(!TOPO_PATH || !(TOPO_PATH.nodeIds || []).length){
      pathSummary.innerHTML = '<div class="empty-state">No active path overlay.</div>';
      return;
    }
    var nodeNames = (TOPO_PATH.nodeIds || []).map(function(id){ return (graphNodeById(id) || nById(id)).name || id; }).join(' → ');
    pathSummary.innerHTML = rows([
      ['Nodes', String((TOPO_PATH.nodeIds || []).length)],
      ['Links', String((TOPO_PATH.linkIds || []).length)],
      ['Score', Number(TOPO_PATH.total_score || 0).toFixed(3)],
      ['Route', nodeNames || '-']
    ]);
  }
};

window.showGraphNode = function showGraphNode(id){
  var node = graphNodeById(id) || nById(id);
  if(!node) return;
  var metrics = node.metrics || {};
  openDP(node.name || 'Topology Node',
    rows([
      ['ID', node.id],
      ['Role', node.role || '-'],
      ['Status', node.status || '-'],
      ['Management Address', node.management_address || '-'],
      ['Last Seen', node.last_seen_at ? fmtTime(node.last_seen_at) : '-'],
      ['Ping', metrics.ping_ms != null ? (Number(metrics.ping_ms).toFixed(1) + ' ms') : '-'],
      ['Load', metrics.load_ratio != null ? Number(metrics.load_ratio).toFixed(3) : '-'],
      ['Peers Online', String(metrics.peer_count || 0)],
      ['Peers Total', String(metrics.peer_count_total || 0)]
    ])
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="showNode(\''+esc(node.id)+'\')">NODE DETAIL</button>'
      +'<button class="btn pri" onclick="openPathPlanner(\''+esc(node.id)+'\')">PLAN FROM</button>'
    +'</div>',
    { kind:'topology-node', id:node.id }
  );
};

window.showGraphEdge = function showGraphEdge(id){
  var edge = graphEdgeById(id) || linkById(id);
  if(!edge) return;
  var metrics = edge.metrics || {};
  openDP(edge.name || 'Topology Link',
    rows([
      ['ID', edge.id],
      ['Driver', edge.driver_name || edge.driver || '-'],
      ['Topology', edge.topology_type || edge.topo || '-'],
      ['State', edge.state || '-'],
      ['Left Node', nById(edge.left_node_id || edge.left).name],
      ['Right Node', nById(edge.right_node_id || edge.right).name],
      ['Left Interface', edge.left_interface || edge.leftInterface || '-'],
      ['Right Interface', edge.right_interface || edge.rightInterface || '-'],
      ['Latency', metrics.latency_ms != null ? (Number(metrics.latency_ms).toFixed(1) + ' ms') : '-'],
      ['Load', metrics.load_ratio != null ? Number(metrics.load_ratio).toFixed(3) : '-'],
      ['Loss', metrics.loss_pct != null ? (Number(metrics.loss_pct).toFixed(2) + '%') : '-']
    ])
    +'<div class="dp-actions">'
      +'<button class="btn" onclick="showLink(\''+esc(edge.id)+'\')">LINK DETAIL</button>'
      +'<button class="btn pri" onclick="actionLinkApply(\''+esc(edge.id)+'\')">APPLY</button>'
    +'</div>',
    { kind:'topology-link', id:edge.id }
  );
};

window.renderTopologyEdges = function renderTopologyEdges(pos, graphEdges, edgeG, mk){
  while(edgeG.firstChild) edgeG.removeChild(edgeG.firstChild);
  graphEdges.forEach(function(l){
    var a = pos[l.left_node_id], b = pos[l.right_node_id];
    if(!a||!b) return;
    var inPath = !!(TOPO_PATH && (TOPO_PATH.linkIds||[]).indexOf(l.id) !== -1);
    var mx = (a.x+b.x)/2, my = (a.y+b.y)/2;
    var metrics = l.metrics || {};
    var edgeColor = inPath ? 'rgba(77,166,255,0.9)' : (l.state==='active' ? 'rgba(0,200,180,0.35)' : 'rgba(255,69,96,0.35)');
    var edgeWidth = inPath ? 3 : 1.5;
    var edgeDash = inPath ? 'none' : '6,5';
    var g = mk('g', {'data-edge-id': l.id});
    edgeG.appendChild(g);

    var line = mk('line',{
      x1:a.x, y1:a.y, x2:b.x, y2:b.y,
      stroke: edgeColor,
      'stroke-width': edgeWidth,
      'stroke-dasharray': edgeDash,
      'pointer-events':'none'
    });
    g.appendChild(line);

    var hit = mk('line',{
      x1:a.x, y1:a.y, x2:b.x, y2:b.y,
      stroke:'rgba(0,0,0,0)',
      'stroke-width':'18',
      'stroke-linecap':'round',
      style:'cursor:pointer'
    });
    hit.addEventListener('click', function(){ showGraphEdge(l.id); });
    g.appendChild(hit);

    var labelText = String(l.name || l.driver_name || l.driver || '-');
    var label = mk('text',{
      x:mx, y:my-12,
      'text-anchor':'middle',
      fill: inPath ? '#4da6ff' : '#f0f6fc',
      'font-size':'12',
      'font-weight':'bold',
      'font-family':'Courier New,monospace',
      style:'cursor:pointer'
    });
    label.textContent = labelText;
    g.appendChild(label);

    var labelBox = mk('rect',{
      rx:'3',
      ry:'3',
      fill:'rgba(8,12,16,0.96)',
      stroke: inPath ? 'rgba(77,166,255,0.55)' : 'rgba(0,220,200,0.35)',
      'stroke-width':'1',
      style:'cursor:pointer'
    });
    g.insertBefore(labelBox, label);

    var labelPadX = 8;
    var labelPadY = 4;
    try{
      var bbox = label.getBBox();
      labelBox.setAttribute('x', bbox.x - labelPadX);
      labelBox.setAttribute('y', bbox.y - labelPadY);
      labelBox.setAttribute('width', bbox.width + labelPadX * 2);
      labelBox.setAttribute('height', bbox.height + labelPadY * 2);
    }catch(_e){}
    labelBox.addEventListener('click', function(){ showGraphEdge(l.id); });
    label.addEventListener('click', function(){ showGraphEdge(l.id); });

    var tiface = mk('text',{
      x:mx, y:my+9,
      'text-anchor':'middle',
      fill:'#b8d0e8',
      'font-size':'11',
      'font-family':'Courier New,monospace',
      'pointer-events':'none'
    });
    tiface.textContent = (l.left_interface||'?') + '→' + (l.right_interface||'?');
    g.appendChild(tiface);

    var lat = metrics.latency_ms != null ? Number(metrics.latency_ms).toFixed(1)+'ms' : null;
    if(lat){
      var tmet = mk('text',{
        x:mx, y:my+23,
        'text-anchor':'middle',
        fill:'rgba(184,208,232,0.65)',
        'font-size':'10',
        'font-family':'Courier New,monospace',
        'pointer-events':'none'
      });
      tmet.textContent = lat + (metrics.loss_pct != null ? ' / '+Number(metrics.loss_pct).toFixed(1)+'%' : '');
      g.appendChild(tmet);
    }
  });
};

window.drawTopo = function drawTopo(){
  var svg = document.getElementById('tc');
  if(!svg){ return; }
  var W = svg.getBoundingClientRect().width || 900;
  var wrap = svg.parentElement;
  var wrapHeight = wrap ? Math.round(wrap.getBoundingClientRect().height || 0) : 0;
  var H = Math.max(300, wrapHeight || 320);
  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H);
  svg.setAttribute('height', H);
  svg._viewWidth = W;
  svg._viewHeight = H;

  var graphNodes = GRAPH_DATA.nodes || [];
  var graphEdges = GRAPH_DATA.edges || [];

  // Keep existing user-dragged positions, only init new nodes
  if(!svg._nodePos) svg._nodePos = {};
  var pos = svg._nodePos;
  var existing = Object.keys(pos);
  var allIds = graphNodes.map(function(n){ return n.id; });
  // Remove stale
  existing.forEach(function(id){ if(allIds.indexOf(id) === -1) delete pos[id]; });
  // Init missing via hierarchical layout (gateway → relay → egress rows)
  var missing = graphNodes.filter(function(n){ return !pos[n.id]; });
  if(missing.length){
    var rowOrder = ['gateway', 'relay', 'egress', 'mixed'];
    var byRole = {gateway: [], relay: [], egress: [], mixed: []};
    missing.forEach(function(n){
      var r = n.role && byRole[n.role] !== undefined ? n.role : 'mixed';
      byRole[r].push(n);
    });
    var rows = rowOrder.filter(function(r){ return byRole[r].length > 0; });
    var rowCount = rows.length || 1;
    rows.forEach(function(role, ri){
      var rNodes = byRole[role];
      var colStep = W / (rNodes.length + 1);
      var rowY = H * (ri + 1) / (rowCount + 1);
      rNodes.forEach(function(n, ci){
        pos[n.id] = {x: colStep * (ci + 1), y: rowY};
      });
    });
  }

  var sc = {reachable:'#00e676',degraded:'#f5a623',offline:'#ff4560',unreachable:'#ff4560',unknown:'#6e8fa8'};
  var ns = 'http://www.w3.org/2000/svg';

  function mk(tag, attrs){
    var el = document.createElementNS(ns, tag);
    Object.keys(attrs).forEach(function(k){ el.setAttribute(k, attrs[k]); });
    return el;
  }

  // Clear and rebuild
  while(svg.firstChild) svg.removeChild(svg.firstChild);

  // Defs for arrowhead
  var defs = mk('defs',{});
  var marker = mk('marker',{id:'arr',markerWidth:'8',markerHeight:'8',refX:'6',refY:'3',orient:'auto'});
  var markerPath = mk('path',{d:'M0,0 L0,6 L8,3 z',fill:'rgba(0,200,180,0.5)'});
  marker.appendChild(markerPath);
  defs.appendChild(marker);
  svg.appendChild(defs);

  var panSurface = mk('rect',{
    x:0, y:0, width:W, height:H,
    fill:'rgba(0,0,0,0)',
    style:'cursor:grab'
  });
  svg._topoPanSurface = panSurface;
  svg.appendChild(panSurface);

  var worldG = mk('g',{id:'topo-world'});
  svg._topoWorld = worldG;
  svg.appendChild(worldG);

  // Edge layer group
  var edgeG = mk('g',{id:'topo-edges'});
  worldG.appendChild(edgeG);
  // Node layer group (on top)
  var nodeG = mk('g',{id:'topo-nodes'});
  worldG.appendChild(nodeG);

  renderTopologyEdges(pos, graphEdges, edgeG, mk);

  // Draw nodes
  graphNodes.forEach(function(n){
    var p = pos[n.id];
    var col = sc[n.status] || '#6e8fa8';
    var ri = {gateway:'G',relay:'R',egress:'E',mixed:'M'}[n.role] || '?';
    var R = 26;

    var g = mk('g',{
      id:'topo-node-'+n.id,
      transform:'translate('+p.x+','+p.y+')',
      style:'cursor:grab'
    });

    // Traffic warning badge
    var nodeData = NODES.find(function(nd){ return nd.id === n.id; }) || {};
    var trafficState = getNodeTrafficState(nodeData);
    if(trafficState){
      var badgeColor = trafficState === 'crit' ? '#ff4560' : '#f5a623';
      // Triangle
      var tri = mk('polygon',{
        points:'0,-'+( R+22)+' -10,-'+(R+6)+' 10,-'+(R+6),
        fill:badgeColor, opacity:'0.92'
      });
      g.appendChild(tri);
      // Exclamation
      var exc = mk('text',{
        x:0, y:-(R+8),
        'text-anchor':'middle','dominant-baseline':'central',
        fill:'#080c10','font-size':'11','font-weight':'bold',
        'font-family':'Courier New,monospace',style:'pointer-events:none'
      });
      exc.textContent = '!';
      g.appendChild(exc);
      // Label
      var warnLbl = mk('text',{
        x:0, y:-(R+26),
        'text-anchor':'middle',
        fill:badgeColor,'font-size':'10','font-weight':'bold',
        'font-family':'Courier New,monospace',style:'pointer-events:none'
      });
      warnLbl.textContent = 'Traffic';
      g.appendChild(warnLbl);
    }

    // Outer ring glow
    var glow = mk('circle',{r:R+4, fill:'none', stroke:col, 'stroke-width':'1', opacity:'0.2'});
    g.appendChild(glow);

    // Main circle
    var circle = mk('circle',{r:R, fill:'#111820', stroke:col, 'stroke-width':'1.5'});
    g.appendChild(circle);

    // Role letter
    var letter = mk('text',{
      x:0, y:0,
      'text-anchor':'middle',
      'dominant-baseline':'central',
      fill:col,
      'font-size':'16',
      'font-weight':'bold',
      'font-family':'Courier New,monospace',
      style:'pointer-events:none'
    });
    letter.textContent = ri;
    g.appendChild(letter);

    // Status dot
    var dot = mk('circle',{cx:R-2, cy:-(R-2), r:4.5, fill:col});
    g.appendChild(dot);

    // Name label
    var label = mk('text',{
      x:0, y:R+16,
      'text-anchor':'middle',
      fill:'#f0f6fc',
      'font-size':'12',
      'font-weight':'600',
      'font-family':'Courier New,monospace',
      style:'pointer-events:none'
    });
    label.textContent = n.name;
    g.appendChild(label);

    // Load label
    var metrics = n.metrics || {};
    var loadPct = Math.round((metrics.load_ratio||0)*100);
    var loadColor = loadPct > 80 ? '#ff4560' : loadPct > 50 ? '#f5a623' : '#00e676';
    var loadLbl = mk('text',{
      id:'topo-load-'+n.id,
      x:0, y:R+30,
      'text-anchor':'middle',
      fill:loadColor,
      'font-size':'11',
      'font-family':'Courier New,monospace',
      style:'pointer-events:none'
    });
    loadLbl.textContent = 'CPU ' + loadPct + '%';
    g.appendChild(loadLbl);

    // Peers online label
    var peersOnlineLbl = mk('text',{
      id:'topo-peers-'+n.id,
      x:0, y:R+44,
      'text-anchor':'middle',
      fill:'#00e676',
      'font-size':'11',
      'font-family':'Courier New,monospace',
      style:'pointer-events:none'
    });
    peersOnlineLbl.textContent = (metrics.peer_count||0) + ' online';
    g.appendChild(peersOnlineLbl);

    // Peers total label
    var peersTotalLbl = mk('text',{
      id:'topo-peers-total-'+n.id,
      x:0, y:R+57,
      'text-anchor':'middle',
      fill:'#6e8fa8',
      'font-size':'11',
      'font-family':'Courier New,monospace',
      style:'pointer-events:none'
    });
    peersTotalLbl.textContent = (metrics.peer_count_total||0) + ' total';
    g.appendChild(peersTotalLbl);

    // Click
    g.addEventListener('click', function(e){
      if(g._dragged){ g._dragged = false; return; }
      showGraphNode(n.id);
    });

    // Drag
    var dragging = false;
    var dragStart = null;
    g.addEventListener('mousedown', function(e){
      if(e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      dragging = true;
      g._dragged = false;
      dragStart = {mx: e.clientX, my: e.clientY, px: pos[n.id].x, py: pos[n.id].y};
      g.style.cursor = 'grabbing';
      svg.style.cursor = 'grabbing';
    });
    svg.addEventListener('mousemove', function(e){
      if(!dragging) return;
      var scale = clampTopologyZoom(TOPO_ZOOM || 1);
      var dx = (e.clientX - dragStart.mx) / scale;
      var dy = (e.clientY - dragStart.my) / scale;
      if(Math.abs(dx) > 3 || Math.abs(dy) > 3) g._dragged = true;
      pos[n.id].x = Math.max(R+4, Math.min(W-R-4, dragStart.px + dx));
      pos[n.id].y = Math.max(R+4, Math.min(H-R-20, dragStart.py + dy));
      // Update this node position
      g.setAttribute('transform','translate('+pos[n.id].x+','+pos[n.id].y+')');
      // Redraw edges only
      _redrawEdges(pos, graphEdges, edgeG, ns, mk);
    });
    svg.addEventListener('mouseup', function(){
      if(dragging){
        dragging = false;
        g.style.cursor='grab';
        svg.style.cursor='grab';
        if(g._dragged) window.scheduleTopologyPosSave(pos);
      }
    });

    nodeG.appendChild(g);
  });

  // Path score overlay
  if(TOPO_PATH){
    var scoreT = mk('text',{
      x:14, y:24,
      fill:'rgba(77,166,255,1)',
      'font-size':'13',
      'font-weight':'bold',
      'font-family':'Courier New,monospace'
    });
    scoreT.textContent = 'PATH SCORE: ' + Number(TOPO_PATH.total_score||0).toFixed(3);
    svg.appendChild(scoreT);
  }

  bindTopologyPan(svg);
  bindTopologyZoom(svg);
  applyTopologyZoom(svg);
  renderTopologyMeta();
};

// ── Missing helpers (were in old monolith scope) ─────────────────────────────

function graphNodeById(id){
  return (window.GRAPH_DATA.nodes || []).find(function(n){ return n.id === id; }) || null;
}

function graphEdgeById(id){
  return (window.GRAPH_DATA.edges || []).find(function(e){ return e.id === id; }) || null;
}

function getNodeTrafficState(n){
  if(!n || !n.traffic_limit_gb || n.traffic_used_gb == null) return null;
  var pct = n.traffic_used_gb / n.traffic_limit_gb;
  if(pct >= 1.0) return 'crit';
  if(pct >= 0.8) return 'warn';
  return null;
}

function _redrawEdges(pos, graphEdges, edgeG, ns, mk){
  renderTopologyEdges(pos, graphEdges, edgeG, mk);
}

function _updateNodeMetricLabels(){
  (window.GRAPH_DATA.nodes || []).forEach(function(n){
    var m = n.metrics || {};
    var loadEl = document.getElementById('topo-load-' + n.id);
    var peersEl = document.getElementById('topo-peers-' + n.id);
    if(loadEl){
      var pct = Math.round((m.load_ratio || 0) * 100);
      loadEl.textContent = 'CPU ' + pct + '%';
      loadEl.setAttribute('fill', pct > 80 ? '#ff4560' : pct > 50 ? '#f5a623' : '#00e676');
    }
    if(peersEl){
      peersEl.textContent = (m.peer_count || 0) + ' peers';
    }
  });
}

function bindTopologyPan(svg){
  if(!svg || svg._panBound) return;
  var dragging = false;
  var dragStart = null;
  function stopPan(){
    if(!dragging) return;
    dragging = false;
    svg.style.cursor = 'grab';
  }
  svg.addEventListener('mousedown', function(event){
    if(event.button !== 0) return;
    if(event.target !== svg && event.target !== svg._topoPanSurface) return;
    event.preventDefault();
    dragging = true;
    dragStart = {
      mx: event.clientX,
      my: event.clientY,
      px: window.TOPO_PAN_X,
      py: window.TOPO_PAN_Y
    };
    svg.style.cursor = 'grabbing';
  });
  window.addEventListener('mousemove', function(event){
    if(!dragging || !dragStart) return;
    window.TOPO_PAN_X = dragStart.px + (event.clientX - dragStart.mx);
    window.TOPO_PAN_Y = dragStart.py + (event.clientY - dragStart.my);
    applyTopologyZoom(svg);
  });
  window.addEventListener('mouseup', stopPan);
  window.addEventListener('mouseleave', stopPan);
  svg._panBound = true;
}

async function submitPathPlanner(fd){
  try{
    var response = await window.apiFetch(window.API_PREFIX + '/paths/plan', {
      method: 'POST',
      body: {
        source_node_id: String(fd.get('source_node_id') || '').trim(),
        destination_node_id: String(fd.get('destination_node_id') || '').trim(),
        max_hops: Number(fd.get('max_hops') || 8),
        require_active_links: fd.get('require_active_links') === 'on',
        avoid_node_ids: (fd.get('avoid_node_ids') || '').split(',').map(function(s){ return s.trim(); }).filter(Boolean),
        latency_weight: Number(fd.get('latency_weight') || 1),
        load_weight: Number(fd.get('load_weight') || 1.2),
        loss_weight: Number(fd.get('loss_weight') || 1.5)
      }
    });
    window.TOPO_PATH = {
      nodeIds: response.node_path || [],
      linkIds: (response.hops || []).map(function(h){ return h.link_id; }),
      total_score: response.total_score
    };
    window.closeModal();
    renderTopologyMeta();
    window.drawTopo();
    window.pushEv?.('topology.path', 'planned path with ' + String((response.hops || []).length) + ' hops');
  }catch(err){
    window.pushEv?.('topology.path.error', 'path planning failed: ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
}

window.openPathPlanner = function openPathPlanner(defaultSourceId){
  if((window.GRAPH_DATA.nodes || []).length < 2){
    alert('At least two topology nodes are required.');
    return;
  }
  var nodeOptions = window.GRAPH_DATA.nodes.map(function(node){ return {value: node.id, label: node.name}; });
  var fallbackDest = window.GRAPH_DATA.nodes.find(function(node){ return node.id !== defaultSourceId; });
  var body = '<form id="pathPlannerForm"><div class="modal-grid">'
    + window.formSelect('Source node', 'source_node_id', defaultSourceId || (window.GRAPH_DATA.nodes[0] && window.GRAPH_DATA.nodes[0].id), nodeOptions)
    + window.formSelect('Destination node', 'destination_node_id', fallbackDest ? fallbackDest.id : (window.GRAPH_DATA.nodes[1] && window.GRAPH_DATA.nodes[1].id), nodeOptions)
    + window.formInput('Max hops', 'max_hops', '8', {type: 'number'})
    + window.formCheckbox('Active links only', 'require_active_links', true, {caption: 'Require active links'})
    + window.formInput('Latency weight', 'latency_weight', '1.0', {type: 'number'})
    + window.formInput('Load weight', 'load_weight', '1.2', {type: 'number'})
    + window.formInput('Loss weight', 'loss_weight', '1.5', {type: 'number'})
    + window.formTextarea('Avoid node IDs (CSV)', 'avoid_node_ids', '', {full: true})
    + '</div></form>';
  window.openModal('Plan Path', body, {
    buttons: [
      {label: 'Clear Overlay', className: 'btn', onClick: function(){ window.TOPO_PATH = null; window.closeModal(); renderTopologyMeta(); window.drawTopo(); }},
      {label: 'Cancel', className: 'btn', onClick: window.closeModal},
      {label: 'Plan', className: 'btn pri', onClick: function(){ document.getElementById('pathPlannerForm').requestSubmit(); }}
    ]
  });
  window.bindModalForm('pathPlannerForm', function(fd){ submitPathPlanner(fd); });
};

// ── DEMO MODE DATA ───────────────────────────────────────────────────────────

window.DEMO_MODE = false;
window.DEMO_USER = 'admin';
window.DEMO_NODES = [
  {id:'n1',name:'gw-ams-01',role:'gateway',management_address:'10.0.0.1',ssh_host:'185.12.44.1',ssh_port:22,ssh_user:'root',auth_type:'key',status:'reachable',caps:['awg','wg'],registered_at:'2024-01-15T00:00:00Z',traffic_limit_gb:500,traffic_used_gb:412},
  {id:'n2',name:'relay-fra-01',role:'relay',management_address:'10.0.0.2',ssh_host:'195.22.11.4',ssh_port:22,ssh_user:'root',auth_type:'key',status:'reachable',caps:['awg'],registered_at:'2024-02-01T00:00:00Z',traffic_limit_gb:300,traffic_used_gb:88},
  {id:'n3',name:'egress-lon-01',role:'egress',management_address:'10.0.0.3',ssh_host:'91.108.4.5',ssh_port:22,ssh_user:'root',auth_type:'key',status:'degraded',caps:['wg','xray'],registered_at:'2024-03-10T00:00:00Z',traffic_limit_gb:200,traffic_used_gb:201},
  {id:'n4',name:'gw-sin-01',role:'gateway',management_address:'10.0.0.4',ssh_host:'103.21.55.8',ssh_port:22,ssh_user:'root',auth_type:'key',status:'reachable',caps:['awg','openvpn'],registered_at:'2024-01-20T00:00:00Z',traffic_limit_gb:400,traffic_used_gb:120},
  {id:'n5',name:'relay-nyc-01',role:'relay',management_address:'10.0.0.5',ssh_host:'45.32.18.22',ssh_port:22,ssh_user:'root',auth_type:'key',status:'reachable',caps:['awg','hysteria2'],registered_at:'2024-02-15T00:00:00Z',traffic_limit_gb:250,traffic_used_gb:195},
];
window.DEMO_LINKS = [
  {id:'l1',name:'ams-fra-p2p',driver_name:'awg',left_node_id:'n1',right_node_id:'n2',topology_type:'p2p',state:'active',left_interface:'awg0',right_interface:'awg0'},
  {id:'l2',name:'fra-lon-relay',driver_name:'awg',left_node_id:'n2',right_node_id:'n3',topology_type:'relay',state:'active',left_interface:'awg1',right_interface:'awg0'},
  {id:'l3',name:'sin-nyc-upstream',driver_name:'wg',left_node_id:'n4',right_node_id:'n5',topology_type:'upstream',state:'active',left_interface:'wg0',right_interface:'wg0'},
  {id:'l4',name:'ams-lon-backup',driver_name:'wg',left_node_id:'n1',right_node_id:'n3',topology_type:'p2p',state:'active',left_interface:'wg0',right_interface:'wg1'},
  {id:'l5',name:'nyc-fra-mesh',driver_name:'awg',left_node_id:'n5',right_node_id:'n2',topology_type:'relay',state:'active',left_interface:'awg0',right_interface:'awg2'},
];
window.DEMO_JOBS = [
  {id:'j1',kind:'link.deploy',target_type:'link',target_id:'l1',state:'succeeded',created_at:new Date(Date.now()-7200000).toISOString(),log:[{message:'SSH connected to gw-ams-01'},{message:'Config rendered'},{message:'AWG interface up'},{message:'Handshake established'}]},
  {id:'j2',kind:'node.probe',target_type:'node',target_id:'n3',state:'failed',created_at:new Date(Date.now()-3600000).toISOString(),log:[{message:'Probing egress-lon-01'},{message:'SSH timeout after 10s'},{message:'Probe failed'}]},
  {id:'j3',kind:'link.deploy',target_type:'link',target_id:'l3',state:'running',created_at:new Date(Date.now()-600000).toISOString(),log:[{message:'Job dispatched'},{message:'Rendering WireGuard config'}]},
];
window.DEMO_POLICIES = [
  {id:'p1',name:'ams-nexthop',node_id:'n1',action:'next_hop',priority:10,enabled:true},
  {id:'p2',name:'fra-balancer',node_id:'n2',action:'balancer',priority:20,enabled:true},
  {id:'p3',name:'sin-direct',node_id:'n4',action:'direct',priority:5,enabled:true},
];
window.DEMO_DNS = [
  {id:'d1',route_policy_id:'p1',dns_address:'1.1.1.1',enabled:true},
  {id:'d2',route_policy_id:'p3',dns_address:'8.8.8.8',enabled:false},
];
window.DEMO_REGISTRATIONS = [
  {id:'r1',username:'alex_k',email:'alex@example.com',created_at:new Date(Date.now()-86400000).toISOString(),referral_code:'ONX-2024-A1',device_count:3,status:'pending'},
  {id:'r2',username:'marina_v',email:'marina@vpnuser.net',created_at:new Date(Date.now()-172800000).toISOString(),referral_code:'ONX-2024-B7',device_count:1,status:'pending'},
  {id:'r3',username:'test_user',email:'test@demo.io',created_at:new Date(Date.now()-259200000).toISOString(),referral_code:'',device_count:2,status:'approved'},
];
window.DEMO_PEERS = [
  {id:'p1',username:'alex_k',email:'alex@example.com',node_id:'n1',registered_at:'2024-06-01T12:00:00Z',config_expires_at:'2025-06-01T12:00:00Z',last_ip:'91.234.12.55',traffic_24h_mb:342,traffic_month_mb:8820,config:'[Interface]\nPrivateKey = DEMO_KEY_ALEX\nAddress = 10.8.0.2/24\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = DEMO_SERVER_PUBKEY\nEndpoint = 185.12.44.1:51820\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25'},
  {id:'p2',username:'marina_v',email:'marina@vpnuser.net',node_id:'n2',registered_at:'2024-07-15T09:00:00Z',config_expires_at:'2025-07-15T09:00:00Z',last_ip:'178.44.210.3',traffic_24h_mb:128,traffic_month_mb:3210,config:'[Interface]\nPrivateKey = DEMO_KEY_MARINA\nAddress = 10.8.0.3/24\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = DEMO_SERVER_PUBKEY\nEndpoint = 195.22.11.4:51820\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25'},
  {id:'p3',username:'test_user',email:'test@demo.io',node_id:'n1',registered_at:'2024-08-20T14:30:00Z',config_expires_at:'2024-12-31T23:59:00Z',last_ip:'5.100.44.12',traffic_24h_mb:0,traffic_month_mb:540,config:'[Interface]\nPrivateKey = DEMO_KEY_TEST\nAddress = 10.8.0.4/24\nDNS = 8.8.8.8\n\n[Peer]\nPublicKey = DEMO_SERVER_PUBKEY\nEndpoint = 185.12.44.1:51820\nAllowedIPs = 10.0.0.0/8\nPersistentKeepalive = 25'},
  {id:'p4',username:'ivan_p',email:'ivan@corp.ru',node_id:'n3',registered_at:'2024-09-05T08:00:00Z',config_expires_at:'2025-09-05T08:00:00Z',last_ip:'212.47.88.201',traffic_24h_mb:891,traffic_month_mb:14200,config:'[Interface]\nPrivateKey = DEMO_KEY_IVAN\nAddress = 10.8.0.5/24\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = DEMO_SERVER_PUBKEY\nEndpoint = 91.108.4.5:51820\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25'},
  {id:'p5',username:'sarah_m',email:'sarah@example.org',node_id:'n4',registered_at:'2024-10-10T16:00:00Z',config_expires_at:'2025-10-10T16:00:00Z',last_ip:'104.28.55.99',traffic_24h_mb:210,traffic_month_mb:5600,config:'[Interface]\nPrivateKey = DEMO_KEY_SARAH\nAddress = 10.8.0.6/24\nDNS = 1.1.1.1\n\n[Peer]\nPublicKey = DEMO_SERVER_PUBKEY\nEndpoint = 103.21.55.8:51820\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 25'},
];
window.DEMO_GRAPH = {
  nodes: DEMO_NODES.map(function(n){
    var peerMap = {n1:3,n2:4,n3:1,n4:2,n5:3};
    return {
      id:n.id, name:n.name, role:n.role, status:n.status,
      management_address:n.management_address,
      metrics:{ load_ratio: 0.2 + Math.random()*0.5, peer_count: peerMap[n.id]||0 }
    };
  }),
  edges: DEMO_LINKS.map(function(l){ return {id:l.id,name:l.name,left_node_id:l.left_node_id,right_node_id:l.right_node_id,driver_name:l.driver_name,topology_type:l.topology_type,state:l.state,left_interface:l.left_interface,right_interface:l.right_interface,metrics:{}}; }),
  generated_at: new Date().toISOString()
};

// Live metrics ticker for demo — updates load_ratio every 3s and redraws topo
var _demoMetricsTick = null;
window.startDemoMetricsTicker = function startDemoMetricsTicker(){
  if(_demoMetricsTick) clearInterval(_demoMetricsTick);
  _demoMetricsTick = setInterval(function(){
    var peerMap = {n1:3,n2:4,n3:1,n4:2,n5:3};
    (GRAPH_DATA.nodes||[]).forEach(function(n){
      if(!n.metrics) n.metrics = {};
      // Fluctuate load ±0.05, clamp 0.03–0.97
      var cur = n.metrics.load_ratio != null ? n.metrics.load_ratio : 0.3;
      n.metrics.load_ratio = Math.max(0.03, Math.min(0.97, cur + (Math.random()-0.5)*0.1));
      n.metrics.peer_count = peerMap[n.id] || 0;
    });
    // Only redraw if topology page is active
    var topoPage = document.getElementById('page-topology');
    if(topoPage && topoPage.classList.contains('active')){
      _updateNodeMetricLabels();
    }
  }, 3000);
};

export {};
