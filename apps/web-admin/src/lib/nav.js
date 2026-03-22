// nav.js — Two-level navigation, group/page switching, hash router

window.NAV_GROUPS = {
  system:   { label:'System',         pages:['system','tickets'],
              subs:[
                {p:'system',  label:'Main'},
                {p:'tickets', label:'Support Chat', badge:'supportBadge'},
              ]},
  network:  { label:'Network',        pages:['routing-summary','nodes','traffic','links','policies','transit','jobs'],
              subs:[
                {p:'routing-summary', label:'Routing Summary'},
                {p:'nodes',    label:'Nodes',            badge:'nbn'},
                {p:'traffic',  label:'Node Traffic'},
                {p:'links',    label:'Links',            badge:'lbn'},
                {p:'policies', label:'Policies'},
                {p:'transit',  label:'Transit Policies'},
                {p:'jobs',     label:'Jobs',             badge:'jbn'},
              ]},
  access:   { label:'Access Control', pages:['peers','registrations','users','devices','referral-codes','management','failban','audit'],
              subs:[
                {p:'peers',         label:'Peers',         badge:'peersBadge'},
                {p:'registrations', label:'Registrations', badge:'regBadge'},
                {p:'users',         label:'Users'},
                {p:'devices',       label:'Devices'},
                {p:'referral-codes',label:'Referral Pools'},
                {p:'management',    label:'Management'},
                {p:'failban',       label:'Fail2Ban',      dot:'red'},
                {p:'audit',         label:'Audit / Access'},
              ]},
  services: { label:'Services',       pages:['xray','awg','wg','ovpn','email'],
              subs:[
                {p:'xray',  label:'XRAY'},
                {p:'awg',   label:'AWG'},
                {p:'wg',    label:'WG'},
                {p:'ovpn',  label:'oVPN'},
                {p:'email', label:'E-Mail'},
              ]},
  topology: { label:'Topology',       pages:['topology'], subs:[] },
  debug:    { label:'Debug',          pages:['apidebug'], subs:[] },
};

window.PAGE_TO_GROUP = {};
Object.keys(window.NAV_GROUPS).forEach(function(g){
  window.NAV_GROUPS[g].pages.forEach(function(p){ window.PAGE_TO_GROUP[p] = g; });
});

var _currentGroup = 'system';
var _currentPage  = 'system';

window.switchGroup = function switchGroup(groupName){
  var grp = window.NAV_GROUPS[groupName];
  if(!grp) return;
  _currentGroup = groupName;

  // Update main group tabs
  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === groupName);
  });

  // Build sub-tabs
  var subBar = document.getElementById('navSub');
  subBar.innerHTML = '';

  if(!grp.subs.length){
    // No sub-tabs — show the single page directly
    window.showPage(grp.pages[0]);
    return;
  }

  grp.subs.forEach(function(sub, idx){
    var el = document.createElement('div');
    el.className = 'nav-sub-item';
    el.setAttribute('data-p', sub.p);

    var label = document.createElement('span');
    label.textContent = sub.label;
    el.appendChild(label);

    if(sub.badge){
      var orig = document.getElementById(sub.badge);
      if(orig){
        var badge = orig.cloneNode(true);
        badge.id = sub.badge + '_sub';
        badge.className = orig.className;
        badge.style.cssText = orig.style.cssText;
        el.appendChild(badge);
      }
    }
    if(sub.dot === 'red'){
      var dot = document.createElement('span');
      dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:var(--red);display:inline-block;margin-left:4px;';
      el.appendChild(dot);
    }

    el.addEventListener('click', function(){
      window.showPage(sub.p);
    });
    subBar.appendChild(el);
  });

  // Show first sub-tab or keep current if in this group
  if(window.PAGE_TO_GROUP[_currentPage] === groupName){
    window.showPage(_currentPage);
  } else {
    window.showPage(grp.subs[0].p);
  }

  // Update hash
  location.hash = '#/' + groupName;
};

window.showPage = function showPage(pageId){
  _currentPage = pageId;

  // Hide all pages, show target
  document.querySelectorAll('.page').forEach(function(p){
    p.classList.toggle('active', p.id === 'page-' + pageId);
  });

  // Activate correct sub-tab
  document.querySelectorAll('.nav-sub-item').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-p') === pageId);
  });

  // Activate correct group tab
  var g = window.PAGE_TO_GROUP[pageId] || pageId;
  document.querySelectorAll('.nav-group-tab').forEach(function(el){
    el.classList.toggle('active', el.getAttribute('data-g') === g);
  });

  if(pageId === 'topology'){
    window.refreshTopology?.().then(window.drawTopo);
    window.startTopologyAutoRefresh?.();
    window.startTopologyMetaRefresh?.();
  } else {
    window.stopTopologyAutoRefresh?.();
    window.stopTopologyMetaRefresh?.();
  }
  window.syncTopologyAutoButton?.();
  if(pageId==='failban'){ window.refreshFailban?.().catch(function(){}); }
  if(pageId==='tickets'){ window.loadSupportTickets?.(); window.startSupportTicketsRefresh?.(); if(window._supportTicketId) window._clearSupportUnread?.(window._supportTicketId); }
  else { window.stopSupportTicketsRefresh?.(); }

  // Update hash: #/groupName/pageId
  var grpName = window.PAGE_TO_GROUP[pageId] || pageId;
  location.hash = '#/' + grpName + '/' + pageId;
};

// ── Hash router ──────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function(){
  var hash = location.hash; // e.g. #/network/nodes or #/system
  if(!hash || hash === '#' || hash === '#/') return;
  var parts = hash.replace(/^#\//, '').split('/');
  var groupName = parts[0] || 'system';
  var pageId = parts[1] || null;
  if(window.NAV_GROUPS[groupName]){
    if(pageId && window.PAGE_TO_GROUP[pageId] === groupName){
      // switchGroup first to build sub-bar, then override page
      window.switchGroup(groupName);
      window.showPage(pageId);
    } else {
      window.switchGroup(groupName);
    }
  }
});

export var switchGroup = window.switchGroup;
export var showPage    = window.showPage;
