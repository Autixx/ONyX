// Login page canvas network animation
(function(){
  var canvas = document.getElementById('loginCanvas');
  if(!canvas) return;
  var ctx = canvas.getContext('2d');
  var W, H, nodes, edges;
  var SIGNALS  = [];
  var TRAILS   = [];
  var GLOWS    = [];
  var N_NODES        = 250;
  var N_CONCURRENT   = 8;
  var SIGNAL_PX_PER_SEC = 100; // constant pixel speed
  var FADE_MS        = 15000;
  var MAX_CONN       = 3;

  function resize(){
    W = canvas.width  = canvas.offsetWidth;
    H = canvas.height = canvas.offsetHeight;
    buildGraph();
    SIGNALS = []; TRAILS = []; GLOWS = [];
    for(var i=0;i<N_CONCURRENT;i++) spawnSignal();
  }

  function buildGraph(){
    nodes = [];
    for(var i=0;i<N_NODES;i++){
      nodes.push({ x:Math.random()*W, y:Math.random()*H, idx:i });
    }
    var edgeSet = new Set();
    nodes.forEach(function(a,i){
      var dists = nodes.map(function(b,j){ return j===i ? Infinity : Math.hypot(a.x-b.x,a.y-b.y); });
      var sorted = dists.map(function(d,j){return{d:d,j:j};}).sort(function(x,y){return x.d-y.d;});
      var count = 0;
      sorted.forEach(function(s){
        if(count >= MAX_CONN) return;
        var key = Math.min(i,s.j)+':'+Math.max(i,s.j);
        if(!edgeSet.has(key)){ edgeSet.add(key); count++; }
      });
    });
    edges = Array.from(edgeSet).map(function(k){
      var p = k.split(':').map(Number);
      return {a:p[0], b:p[1]};
    });
    nodes.forEach(function(n){ n.adj = []; });
    edges.forEach(function(e){
      nodes[e.a].adj.push({edge:e, other:e.b});
      nodes[e.b].adj.push({edge:e, other:e.a});
    });
  }

  function edgeDuration(e){
    var a=nodes[e.a], b=nodes[e.b];
    var len = Math.hypot(a.x-b.x, a.y-b.y);
    return Math.max(60, len / SIGNAL_PX_PER_SEC * 1000); // ms, min 60ms
  }

  function spawnSignal(){
    var e   = edges[Math.floor(Math.random()*edges.length)];
    var dir = Math.random() < 0.5 ? 1 : 0;
    var startNode = dir?e.a:e.b;
    SIGNALS.push({ edge:e, dir:dir, t:0, startTime:performance.now(),
                   duration:edgeDuration(e), fromIdx:startNode, history:[startNode],
                   hasBranch:false });
  }

  var _accColor = '#00c8b4';
  setInterval(function(){
    _accColor = getComputedStyle(document.documentElement).getPropertyValue('--acc').trim() || '#00c8b4';
  }, 800);

  function hexToRgb(hex){
    hex = hex.trim().replace('#','');
    if(hex.length===3) hex=hex.split('').map(function(c){return c+c;}).join('');
    var n=parseInt(hex,16);
    return [(n>>16)&255,(n>>8)&255,n&255];
  }

  function draw(now){
    ctx.clearRect(0,0,W,H);
    var rgb = hexToRgb(_accColor);
    var r=rgb[0],g=rgb[1],b=rgb[2];

    // 1. Dim base edges
    ctx.setLineDash([3,4]);
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = 'rgba('+r+','+g+','+b+',0.055)';
    edges.forEach(function(e){
      var a=nodes[e.a], nb=nodes[e.b];
      ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(nb.x,nb.y); ctx.stroke();
    });
    ctx.setLineDash([]);

    // 2. Dim base nodes
    nodes.forEach(function(n){
      ctx.beginPath(); ctx.arc(n.x,n.y,1.8,0,Math.PI*2);
      ctx.fillStyle='rgba('+r+','+g+','+b+',0.10)'; ctx.fill();
    });

    // 3. Fading edge trails
    TRAILS = TRAILS.filter(function(tr){
      var age = now - tr.litAt;
      if(age >= FADE_MS) return false;
      var alpha = 1 - age/FADE_MS;
      ctx.setLineDash([4,3]);
      ctx.lineWidth = 0.9 + alpha*0.4;
      ctx.strokeStyle = 'rgba('+r+','+g+','+b+','+(0.55*alpha).toFixed(3)+')';
      ctx.beginPath(); ctx.moveTo(tr.x1,tr.y1); ctx.lineTo(tr.x2,tr.y2); ctx.stroke();
      ctx.setLineDash([]);
      return true;
    });

    // 4. Fading node glows
    GLOWS = GLOWS.filter(function(gl){
      var age = now - gl.litAt;
      if(age >= FADE_MS) return false;
      var alpha = 1 - age/FADE_MS;
      var gr = ctx.createRadialGradient(gl.x,gl.y,0,gl.x,gl.y,gl.r);
      gr.addColorStop(0,'rgba('+r+','+g+','+b+','+(0.45*alpha).toFixed(3)+')');
      gr.addColorStop(1,'rgba('+r+','+g+','+b+',0)');
      ctx.beginPath(); ctx.arc(gl.x,gl.y,gl.r,0,Math.PI*2);
      ctx.fillStyle=gr; ctx.fill();
      ctx.beginPath(); ctx.arc(gl.x,gl.y,gl.dotR,0,Math.PI*2);
      ctx.fillStyle='rgba('+r+','+g+','+b+','+(0.85*alpha).toFixed(3)+')'; ctx.fill();
      return true;
    });

    // 5. Active signals
    SIGNALS.forEach(function(sig, idx){
      sig.t = Math.min(1, (now - sig.startTime) / sig.duration);
      var e    = sig.edge;
      var from = nodes[sig.dir ? e.a : e.b];
      var to   = nodes[sig.dir ? e.b : e.a];
      var ex   = from.x + (to.x-from.x)*sig.t;
      var ey   = from.y + (to.y-from.y)*sig.t;

      // Active lit segment
      ctx.setLineDash([4,3]);
      ctx.lineWidth = 1.3;
      ctx.strokeStyle = 'rgba('+r+','+g+','+b+',0.80)';
      ctx.beginPath(); ctx.moveTo(from.x,from.y); ctx.lineTo(ex,ey); ctx.stroke();
      ctx.setLineDash([]);

      // Source node glow
      var gr = ctx.createRadialGradient(from.x,from.y,0,from.x,from.y,11);
      gr.addColorStop(0,'rgba('+r+','+g+','+b+',0.50)');
      gr.addColorStop(1,'rgba('+r+','+g+','+b+',0)');
      ctx.beginPath(); ctx.arc(from.x,from.y,11,0,Math.PI*2); ctx.fillStyle=gr; ctx.fill();
      ctx.beginPath(); ctx.arc(from.x,from.y,2.6,0,Math.PI*2);
      ctx.fillStyle='rgba('+r+','+g+','+b+',0.90)'; ctx.fill();

      // Leading dot
      ctx.beginPath(); ctx.arc(ex,ey,2.2,0,Math.PI*2);
      ctx.fillStyle='rgba('+r+','+g+','+b+',0.88)'; ctx.fill();

      if(sig.t >= 1){
        var destIdx = sig.dir ? e.b : e.a;
        var dest    = nodes[destIdx];

        TRAILS.push({ x1:from.x, y1:from.y, x2:to.x, y2:to.y, litAt:now });
        GLOWS.push({ x:dest.x, y:dest.y, r:12, dotR:3, litAt:now });

        var fromIdx  = sig.fromIdx;
        var history  = sig.history || [];
        var recent   = history.slice(-15);
        var fresh = dest.adj.filter(function(nb){
          return nb.other !== fromIdx && recent.indexOf(nb.other) === -1;
        });
        var forward = fresh.length ? fresh : dest.adj.filter(function(nb){ return nb.other !== fromIdx; });
        var pool = forward.length ? forward : dest.adj;
        var pick     = pool[Math.floor(Math.random()*pool.length)];
        var nextEdge = pick.edge;
        var nextDir  = nextEdge.a === destIdx ? 1 : 0;
        var newHistory = history.concat([destIdx]);
        if(newHistory.length > 15) newHistory = newHistory.slice(newHistory.length - 15);

        var hopsLeft = sig.hopsLeft != null ? sig.hopsLeft - 1 : null;
        if(hopsLeft !== null && hopsLeft <= 0){
          SIGNALS[idx] = null;
        } else {
          var keepBranch = (hopsLeft !== null) ? false : sig.hasBranch;
          SIGNALS[idx] = { edge:nextEdge, dir:nextDir, t:0, startTime:now, duration:edgeDuration(nextEdge), fromIdx:destIdx, history:newHistory,
                           hopsLeft: hopsLeft, hasBranch: keepBranch };
        }

        var canBranch = !sig.hopsLeft && !sig.hasBranch && SIGNALS.filter(function(s){return s!==null;}).length < 16;
        if(canBranch && Math.random() < 0.20){
          var branchPool = fresh.length > 1
            ? fresh.filter(function(nb){ return nb.edge !== nextEdge; })
            : (forward.length > 1 ? forward.filter(function(nb){ return nb.edge !== nextEdge; }) : null);
          if(branchPool && branchPool.length){
            var bpick = branchPool[Math.floor(Math.random()*branchPool.length)];
            var bEdge = bpick.edge;
            var bDir  = bEdge.a === destIdx ? 1 : 0;
            SIGNALS.push({
              edge: bEdge, dir: bDir, t: 0,
              startTime: now, duration: edgeDuration(bEdge),
              fromIdx: destIdx, history: newHistory.slice(),
              hopsLeft: 5,
              hasBranch: false
            });
            if(SIGNALS[idx]) SIGNALS[idx].hasBranch = true;
          }
        }
      }
    });

    SIGNALS = SIGNALS.filter(function(s){ return s !== null; });
    var baseSigs = SIGNALS.filter(function(s){ return s.hopsLeft == null; });
    while(baseSigs.length < N_CONCURRENT && SIGNALS.length < 16){
      spawnSignal();
      baseSigs = SIGNALS.filter(function(s){ return s.hopsLeft == null; });
    }

    requestAnimationFrame(draw);
  }

  window.addEventListener('resize', resize);
  resize();
  requestAnimationFrame(draw);

  var _lw = document.getElementById('loginWrap');
  if(_lw){
    new MutationObserver(function(){
      if(_lw.style.display !== 'none') setTimeout(resize, 60);
    }).observe(_lw, {attributes:true, attributeFilter:['style']});
  }
})();

export {};
