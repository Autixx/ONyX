// Page module - all functions exposed as window globals

window.refreshRoutingSummary = function refreshRoutingSummary(){ renderPolicyTransitHub(); };

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
    var xrayHops = nextHopKinds.xray_service || 0;
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
          ['XRAY next hops', String(xrayHops)],
          ['Link next hops', String(lnkHops)],
        ]);
  }
};

export {};
