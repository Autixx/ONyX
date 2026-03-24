// utils.js — Formatting helpers, shell counters, filter readers

window.sp = function sp(s){
  var m={reachable:'pg',degraded:'pa',offline:'pr',unreachable:'pr',unknown:'pq',active:'pg',banned:'pr',failed:'pr',dead:'pr',deleted:'pq',planned:'pq',validating:'pb',applying:'pb',running:'pb',succeeded:'pg',success:'pg',pending:'pq',cancelled:'pa',rolled_back:'pa'};
  return '<span class="pill '+(m[s]||'pq')+'">'+s+'</span>';
};

window.rp = function rp(r){
  var m={gateway:'pb',relay:'pp',egress:'pa',mixed:'pq'};
  return '<span class="pill '+(m[r]||'pq')+'">'+r+'</span>';
};

window.esc = function esc(v){
  return String(v == null ? '' : v)
    .replace(/&/g,'&amp;')
    .replace(/</g,'&lt;')
    .replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;')
    .replace(/'/g,'&#39;');
};

window.fmtTime = function fmtTime(value){
  if(!value) return '-';
  var d = new Date(value);
  if(isNaN(d.getTime())) return value;
  return d.toLocaleTimeString();
};

window.fmtDateTime = function fmtDateTime(value){
  if(!value) return '-';
  var d = new Date(value);
  if(isNaN(d.getTime())) return value;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString();
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

window.hpBarColor = function hpBarColor(pct){
  var r,g;
  if(pct<=50){ r=Math.round(pct/50*200); g=180; }
  else { r=200; g=Math.round((1-(pct-50)/50)*180); }
  return 'rgb('+r+','+g+',30)';
};

window.rows = function rows(arr){
  return arr.map(function(r){
    return '<div class="drow"><span class="dk">'+window.esc(r[0])+'</span><span class="dv">'+window.esc(r[1])+'</span></div>';
  }).join('');
};

window.updateShellCounters = function updateShellCounters(){
  var nodeBadge = document.getElementById('nbn');
  if(nodeBadge){ nodeBadge.textContent = String(window.NODES.length); }
};

window.getNodeFilters = function getNodeFilters(){
  var search = document.getElementById('nodeSearch');
  var status = document.getElementById('nodeStatusFilter');
  return {
    search: String(search && search.value || '').trim().toLowerCase(),
    status: String(status && status.value || '').trim().toLowerCase()
  };
};

window.getLinkFilters = function getLinkFilters(){
  var search = document.getElementById('linkSearch');
  var state = document.getElementById('linkStateFilter');
  return {
    search: String(search && search.value || '').trim().toLowerCase(),
    state: String(state && state.value || '').trim().toLowerCase()
  };
};

window.getNodeTrafficFilters = function getNodeTrafficFilters(){
  var search = document.getElementById('trafficSearch');
  var state = document.getElementById('trafficStateFilter');
  return {
    search: String(search && search.value || '').trim().toLowerCase(),
    state: String(state && state.value || '').trim().toLowerCase()
  };
};

window.awgDefaultObfuscation = function awgDefaultObfuscation(){
  return {jc:4, jmin:40, jmax:120, s1:20, s2:40, s3:80, s4:120, h1:10101, h2:20202, h3:30303, h4:40404};
};

window.obfValue = function obfValue(obf, key, def){
  var v = obf && obf[key] != null ? obf[key] : def;
  return v != null ? String(v) : '';
};

export var sp                   = window.sp;
export var rp                   = window.rp;
export var esc                  = window.esc;
export var fmtTime              = window.fmtTime;
export var fmtDateTime          = window.fmtDateTime;
export var fmtRelativeAge       = window.fmtRelativeAge;
export var hpBarColor           = window.hpBarColor;
export var rows                 = window.rows;
export var updateShellCounters  = window.updateShellCounters;
export var getNodeFilters       = window.getNodeFilters;
export var getLinkFilters       = window.getLinkFilters;
export var getNodeTrafficFilters    = window.getNodeTrafficFilters;
export var awgDefaultObfuscation    = window.awgDefaultObfuscation;
export var obfValue                 = window.obfValue;
