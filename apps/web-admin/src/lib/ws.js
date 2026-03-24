// ws.js — WebSocket connection, event routing, state indicator

var WS_URL = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + window.API_PREFIX + '/ws/admin/events';
var ws = null;
var wsReconnectTimer = null;

window.pushEv = function pushEv(type, msg, createdAt){
  var now = createdAt ? new Date(createdAt) : new Date();
  var t = window.fmtDateTime(now);
  var cls = (type.indexOf('fail') !== -1 || type.indexOf('error') !== -1 || type.indexOf('err') !== -1) ? 'err' : type.indexOf('system') === 0 ? 'sys' : type.indexOf('audit') === 0 ? 'aud' : 'job';
  window.AUDIT_EVTS.push({t:t,type:type,cls:cls,msg:msg});
  if(window.AUDIT_EVTS.length > 200){ window.AUDIT_EVTS.shift(); }
  window.renderAudit?.();
  window.renderElog?.();
};

window.setWSState = function setWSState(connected, label){
  var dot = document.getElementById('wsd');
  var text = document.getElementById('wsl');
  dot.classList.toggle('off', !connected);
  text.textContent = label;
};

window.disconnectWS = function disconnectWS(){
  if(wsReconnectTimer){
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if(ws){
    try { ws.close(); } catch(_){ }
    ws = null;
  }
  window.setWSState(false, 'WS DISCONNECTED');
};

window.connectWS = function connectWS(){
  window.disconnectWS();
  if(!window.isAuthenticated){ return; }
  window.setWSState(false, 'WS CONNECTING');
  ws = new WebSocket(WS_URL);
  ws.onopen = function(){ window.setWSState(true, 'WS CONNECTED'); };
  ws.onmessage = function(event){
    try{
      var data = JSON.parse(event.data);
      var type = data.type || 'system.event';
      if(type === 'system.ping'){ return; }
      var payload = data.payload || {};
      var msg = payload.message || payload.detail || payload.id || JSON.stringify(payload);
      window.pushEv(type, msg, payload.created_at);
      if(type.indexOf('job.') === 0){ window.refreshJobs?.().catch(function(){}); window.refreshHealth?.().catch(function(){}); }
      if(type.indexOf('link.') === 0){ window.refreshLinks?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('node.') === 0){ window.refreshNodes?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('node.traffic.') === 0){ window.refreshNodes?.().catch(function(){}); window.refreshNodeTrafficSummary?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('registration.') === 0){ window.loadRegistrations?.().catch(function(){}); window.loadUsers?.().catch(function(){}); window.loadSubscriptions?.().catch(function(){}); }
      if(type.indexOf('peer.') === 0){ window.loadPeers?.().catch(function(){}); window.refreshXrayServices?.().catch(function(){}); window.refreshAwgServices?.().catch(function(){}); window.refreshWgServices?.().catch(function(){}); window.refreshOpenvpnCloakServices?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('transit_policy.') === 0){ window.refreshTransitPolicies?.().catch(function(){}); window.refreshXrayServices?.().catch(function(){}); window.refreshAudit?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('awg_service.') === 0){ window.refreshAwgServices?.().catch(function(){}); window.loadPeers?.().catch(function(){}); window.refreshAudit?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('wg_service.') === 0){ window.refreshWgServices?.().catch(function(){}); window.loadPeers?.().catch(function(){}); window.refreshAudit?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('xray_service.') === 0){ window.refreshXrayServices?.().catch(function(){}); window.loadPeers?.().catch(function(){}); window.refreshAudit?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('openvpn_cloak_service.') === 0){ window.refreshOpenvpnCloakServices?.().catch(function(){}); window.loadPeers?.().catch(function(){}); window.refreshAudit?.().catch(function(){}); window.scheduleTopologyRealtimeRefresh?.(); }
      if(type.indexOf('user.') === 0){ window.loadUsers?.().catch(function(){}); window.loadTransportPackages?.().catch(function(){}); }
      if(type.indexOf('subscription.') === 0){ window.loadSubscriptions?.().catch(function(){}); }
      if(type.indexOf('plan.') === 0){ window.loadPlans?.().catch(function(){}); }
      if(type.indexOf('referral_code.') === 0){ window.loadReferralCodes?.().catch(function(){}); }
      if(type.indexOf('device.') === 0){ window.loadDevices?.().catch(function(){}); }
      if(type.indexOf('transport_package.') === 0){ window.loadTransportPackages?.().catch(function(){}); }
      if(type === 'audit.event'){ window.refreshAudit?.().catch(function(){}); }
    }catch(_){ }
  };
  ws.onclose = function(event){
    window.setWSState(false, 'WS DISCONNECTED');
    if(event && event.code === 1008){
      window.authRedirect('Session expired. Please sign in again.');
      return;
    }
    if(window.isAuthenticated){ wsReconnectTimer = setTimeout(window.connectWS, 3000); }
  };
  ws.onerror = function(){ window.setWSState(false, 'WS ERROR'); };
};

export var pushEv      = window.pushEv;
export var setWSState  = window.setWSState;
export var connectWS   = window.connectWS;
export var disconnectWS = window.disconnectWS;
