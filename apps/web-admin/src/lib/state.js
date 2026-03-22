// state.js — Global data arrays and all lookup/helper functions

// ── Global data arrays ──────────────────────────────────────────────────────
window.NODES               = [];
window.LINKS               = [];
window.JOBS                = [];
window.POLICIES            = [];
window.DNS_P               = [];
window.GEO_P               = [];
window.BALANCERS           = [];
window.PEERS               = [];
window.USERS               = [];
window.PLANS               = [];
window.SUBSCRIPTIONS       = [];
window.REFERRAL_CODES      = [];
window.REFERRAL_POOLS      = [];
window.DEVICES             = [];
window.TRANSPORT_PACKAGES  = [];
window.XRAY_SERVICES       = [];
window.TRANSIT_POLICIES    = [];
window.AWG_SERVICES        = [];
window.WG_SERVICES         = [];
window.OVPN_CLOAK_SERVICES = [];
window.NODE_TRAFFIC        = [];
window.AUDIT_EVTS          = [];
window.REGISTRATIONS       = [];
window.JOB_EVENTS          = {};
window.GRAPH_DATA          = {nodes:[], edges:[], generated_at:null};
window.TOPO_HITBOXES       = {nodes:[], edges:[]};
window.TOPO_PATH           = null;

// ── Lookup functions ─────────────────────────────────────────────────────────

window.nById = function nById(id){ return window.NODES.find(function(n){return n.id===id;})||{name:id,role:'unknown'}; };

window.linkById = function linkById(id){ return window.LINKS.find(function(l){ return l.id===id; }) || null; };

window.jobById = function jobById(id){ return window.JOBS.find(function(j){ return j.id===id; }) || null; };

window.policyById = function policyById(id){ return window.POLICIES.find(function(p){ return p.id===id; }) || null; };

window.nodeInterfaceList = function nodeInterfaceList(nodeId){
  var node = window.nById(nodeId);
  var raw = Array.isArray(node.discovered_interfaces) ? node.discovered_interfaces : [];
  var seen = {};
  return raw.map(function(item){ return String(item || '').trim(); }).filter(function(item){
    if(!item || seen[item]) return false;
    seen[item] = true;
    return true;
  });
};

window.nodeGatewayMap = function nodeGatewayMap(nodeId){
  var node = window.nById(nodeId);
  var raw = node && node.discovered_gateways && typeof node.discovered_gateways === 'object' ? node.discovered_gateways : {};
  var normalized = {};
  Object.keys(raw).forEach(function(key){
    var iface = String(key || '').trim().replace(/:$/,'');
    var gateway = String(raw[key] || '').trim();
    if(iface && gateway){ normalized[iface] = gateway; }
  });
  return normalized;
};

window.routePolicyInterfaceOptions = function routePolicyInterfaceOptions(nodeId, currentValue){
  var options = window.nodeInterfaceList(nodeId).map(function(item){ return {value:item, label:item}; });
  var current = String(currentValue || '').trim();
  if(current && !options.some(function(opt){ return String(opt.value) === current; })){
    options.unshift({value:current, label:current + ' (saved)'});
  }
  if(!options.length){
    options = [{value:'', label:'Run Probe SSH first'}];
  }
  return options;
};

window.routePolicyDefaultIngress = function routePolicyDefaultIngress(nodeId, currentValue){
  var current = String(currentValue || '').trim();
  if(current) return current;
  var interfaces = window.nodeInterfaceList(nodeId);
  return interfaces.find(function(item){ return /^(awg|wg|tun|tap)/i.test(item); })
    || interfaces.find(function(item){ return item !== 'lo'; })
    || '';
};

window.routePolicyDefaultTarget = function routePolicyDefaultTarget(nodeId, ingressValue, currentValue){
  var current = String(currentValue || '').trim();
  if(current) return current;
  var ingress = String(ingressValue || '').trim();
  var interfaces = window.nodeInterfaceList(nodeId);
  return interfaces.find(function(item){ return item !== ingress && item !== 'lo'; })
    || interfaces.find(function(item){ return item !== ingress; })
    || '';
};

window.routePolicyDefaultGateway = function routePolicyDefaultGateway(nodeId, targetInterface, currentValue){
  var current = String(currentValue || '').trim();
  if(current) return current;
  var gatewayMap = window.nodeGatewayMap(nodeId);
  var iface = String(targetInterface || '').trim();
  return String(gatewayMap[iface] || '').trim();
};

window.setSelectOptions = function setSelectOptions(selectEl, options, selectedValue){
  if(!selectEl) return;
  selectEl.innerHTML = options.map(function(opt){
    var optionValue = typeof opt === 'string' ? opt : opt.value;
    var optionLabel = typeof opt === 'string' ? opt : opt.label;
    return '<option value="'+window.esc(optionValue)+'" '+(String(optionValue)===String(selectedValue) ? 'selected' : '')+'>'+window.esc(optionLabel)+'</option>';
  }).join('');
};

window.syncRoutePolicyInterfaceSelectors = function syncRoutePolicyInterfaceSelectors(){
  var nodeEl = document.getElementById('node_id');
  var ingressEl = document.getElementById('ingress_interface');
  var targetEl = document.getElementById('target_interface');
  var gatewayEl = document.getElementById('target_gateway');
  if(!nodeEl || !ingressEl || !targetEl) return;
  var nodeId = String(nodeEl.value || '').trim();
  var ingressValue = window.routePolicyDefaultIngress(nodeId, ingressEl.value);
  window.setSelectOptions(ingressEl, window.routePolicyInterfaceOptions(nodeId, ingressValue), ingressValue);
  var targetValue = String(targetEl.value || '').trim();
  if(!targetValue || targetValue === ingressValue){
    targetValue = window.routePolicyDefaultTarget(nodeId, ingressValue, '');
  }
  window.setSelectOptions(targetEl, window.routePolicyInterfaceOptions(nodeId, targetValue), targetValue);
  if(gatewayEl){
    var currentGateway = String(gatewayEl.value || '').trim();
    var initialGateway = String(gatewayEl.getAttribute('data-initial-value') || '').trim();
    var dirtyGateway = gatewayEl.getAttribute('data-dirty') === '1';
    var fallbackGateway = window.routePolicyDefaultGateway(nodeId, targetValue, '');
    if(!dirtyGateway || currentGateway === '' || currentGateway === initialGateway){
      gatewayEl.value = fallbackGateway;
      gatewayEl.setAttribute('data-initial-value', fallbackGateway);
      gatewayEl.setAttribute('data-dirty', '0');
    }
  }
};

window.dnsPolicyById = function dnsPolicyById(id){ return window.DNS_P.find(function(p){ return p.id===id; }) || null; };

window.geoPolicyById = function geoPolicyById(id){ return window.GEO_P.find(function(p){ return p.id===id; }) || null; };

window.balancerById = function balancerById(id){ return window.BALANCERS.find(function(b){ return b.id===id; }) || null; };

window.xrayServiceById = function xrayServiceById(id){ return window.XRAY_SERVICES.find(function(s){ return s.id===id; }) || null; };

window.transitPolicyById = function transitPolicyById(id){ return window.TRANSIT_POLICIES.find(function(s){ return s.id===id; }) || null; };

window.awgServiceById = function awgServiceById(id){ return window.AWG_SERVICES.find(function(s){ return s.id===id; }) || null; };

window.wgServiceById = function wgServiceById(id){ return window.WG_SERVICES.find(function(s){ return s.id===id; }) || null; };

window.openvpnCloakServiceById = function openvpnCloakServiceById(id){ return window.OVPN_CLOAK_SERVICES.find(function(s){ return s.id===id; }) || null; };

window.transportPackageById = function transportPackageById(id){ return window.TRANSPORT_PACKAGES.find(function(p){ return p.id===id; }) || null; };

window.userById = function userById(id){ return window.USERS.find(function(u){ return u.id===id; }) || null; };

window.planById = function planById(id){ return window.PLANS.find(function(p){ return p.id===id; }) || null; };

window.subscriptionById = function subscriptionById(id){ return window.SUBSCRIPTIONS.find(function(s){ return s.id===id; }) || null; };

window.referralCodeById = function referralCodeById(id){ return window.REFERRAL_CODES.find(function(r){ return r.id===id; }) || null; };

window.deviceById = function deviceById(id){ return window.DEVICES.find(function(d){ return d.id===id; }) || null; };

window.findNodeByName = function findNodeByName(name){
  var needle = String(name || '').trim().toLowerCase();
  return window.NODES.find(function(n){
    return String(n.name || '').trim().toLowerCase() === needle;
  }) || null;
};

window.userNameById = function userNameById(id){
  var user = window.userById(id);
  return user ? user.username : id;
};

window.planNameById = function planNameById(id){
  var plan = window.planById(id);
  return plan ? plan.name : (id || '-');
};

window.policyNameById = function policyNameById(id){
  var policy = window.policyById(id);
  return policy ? policy.name : id;
};

export var nById               = window.nById;
export var linkById            = window.linkById;
export var jobById             = window.jobById;
export var policyById          = window.policyById;
export var dnsPolicyById       = window.dnsPolicyById;
export var geoPolicyById       = window.geoPolicyById;
export var balancerById        = window.balancerById;
export var xrayServiceById     = window.xrayServiceById;
export var transitPolicyById   = window.transitPolicyById;
export var awgServiceById      = window.awgServiceById;
export var wgServiceById       = window.wgServiceById;
export var openvpnCloakServiceById  = window.openvpnCloakServiceById;
export var transportPackageById     = window.transportPackageById;
export var userById            = window.userById;
export var planById            = window.planById;
export var subscriptionById    = window.subscriptionById;
export var referralCodeById    = window.referralCodeById;
export var deviceById          = window.deviceById;
export var findNodeByName      = window.findNodeByName;
export var userNameById        = window.userNameById;
export var planNameById        = window.planNameById;
export var policyNameById      = window.policyNameById;
export var nodeInterfaceList   = window.nodeInterfaceList;
export var nodeGatewayMap      = window.nodeGatewayMap;
export var routePolicyInterfaceOptions  = window.routePolicyInterfaceOptions;
export var routePolicyDefaultIngress    = window.routePolicyDefaultIngress;
export var routePolicyDefaultTarget     = window.routePolicyDefaultTarget;
export var routePolicyDefaultGateway    = window.routePolicyDefaultGateway;
export var setSelectOptions             = window.setSelectOptions;
export var syncRoutePolicyInterfaceSelectors = window.syncRoutePolicyInterfaceSelectors;
