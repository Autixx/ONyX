// ONyX Admin Panel — main entry point
// Import order matters: state → api → utils → modal → i18n → theme → nav → ws → pages

import './lib/state.js';
import './lib/api.js';
import './lib/utils.js';
import './lib/modal.js';
import './lib/i18n.js';
import './lib/theme.js';
import './lib/login-canvas.js';
import './lib/nav.js';
import './lib/ws.js';

// Pages
import './pages/system.js';
import './pages/nodes.js';
import './pages/traffic.js';
import './pages/links.js';
import './pages/policies.js';
import './pages/jobs.js';
import './pages/audit.js';
import './pages/topology.js';
import './pages/peers.js';
import './pages/registrations.js';
import './pages/users.js';
import './pages/devices.js';
import './pages/referral.js';
import './pages/management.js';
import './pages/failban.js';
import './pages/transit.js';
import './pages/xray.js';
import './pages/awg.js';
import './pages/wg.js';
import './pages/ovpn.js';
import './pages/agh.js';
import './pages/tickets.js';
import './pages/apidebug.js';
import './pages/clientupdate.js';
import './pages/routing-summary.js';

// ── Shared helpers (peers uses these) ──────────────────────────────────────
window.fmtBytes = function(mb) {
  if (mb == null) return '-';
  if (mb < 1024) return mb.toFixed(0) + ' MB';
  return (mb / 1024).toFixed(2) + ' GB';
};
window.fmtDate = function(v) {
  if (!v) return '-';
  var d = new Date(v);
  if (isNaN(d)) return v;
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};
window.isExpired = function(v) {
  if (!v) return false;
  return new Date(v) < new Date();
};

// ── Data loading ────────────────────────────────────────────────────────────
window.refreshIdentityData = async function() {
  await Promise.all([
    window.loadUsers?.(),
    window.loadPlans?.(),
    window.loadSubscriptions?.(),
    window.loadReferralCodes?.(),
    window.loadDevices?.(),
    window.loadTransportPackages?.(),
  ]);
};

window.loadData = async function() {
  await Promise.all([
    window.refreshNodes?.(),
    window.refreshNodeTrafficSummary?.(),
    window.refreshLinks?.(),
    window.refreshXrayServices?.(),
    window.refreshTransitPolicies?.(),
    window.refreshAwgServices?.(),
    window.refreshWgServices?.(),
    window.refreshOpenvpnCloakServices?.(),
    window.refreshPolicies?.(),
    window.refreshJobs?.(),
    window.refreshAudit?.(),
    window.refreshTopology?.(),
    window.loadPeers?.(),
    window.loadRegistrations?.(),
    window.refreshIdentityData?.(),
    window.updateOpenTicketCount?.(),
  ]);
};

// ── Health polling ──────────────────────────────────────────────────────────
var _healthPollTimer = null;
window.startHealthPolling = function() {
  if (_healthPollTimer) clearInterval(_healthPollTimer);
  _healthPollTimer = setInterval(function() {
    window.refreshHealth?.().catch(function(err) {
      console.warn('health poll failed', err);
    });
  }, 15000);
};

// ── Boot & Login ────────────────────────────────────────────────────────────
window.isAuthenticated = false;

window.doLogin = async function() {
  var u = document.getElementById('iu').value.trim();
  var p = document.getElementById('ip').value;
  var err = document.getElementById('lerr');
  if (!u || !p) {
    err.textContent = window.LANG === 'ru' ? 'Введите имя пользователя и пароль' : 'Enter username and password';
    return;
  }
  err.textContent = '';
  document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATING...') || 'AUTHENTICATING...';
  if (window.DEMO_MODE) {
    await new Promise(function(r) { setTimeout(r, 600); });
    window.DEMO_USER = u;
    await window.bootApp();
    return;
  }
  try {
    await window.apiFetch(window.API_PREFIX + '/auth/login', {
      method: 'POST',
      body: { username: u, password: p },
      redirectOn401: false,
    });
    await window.bootApp();
  } catch (e) {
    err.textContent = e && e.message ? e.message : (window.LANG === 'ru' ? 'Ошибка аутентификации' : 'Authentication failed');
    document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATE') || 'AUTHENTICATE';
  }
};

window.bootApp = async function(sessionMe) {
  var username = window.DEMO_USER || 'admin';
  if (!window.DEMO_MODE) {
    var me = sessionMe;
    if (me === undefined) {
      me = await window.apiFetch(window.API_PREFIX + '/auth/me');
    }
    username = me && me.user && me.user.username ? me.user.username : 'admin';
  }
  window.isAuthenticated = true;
  document.getElementById('loginWrap').style.display = 'none';
  document.getElementById('appWrap').style.display = 'flex';
  document.getElementById('ubtn').textContent = username;
  window.switchGroup('system');
  document.getElementById('lbtn').textContent = window.uiLiteral?.('AUTHENTICATE') || 'AUTHENTICATE';
  document.getElementById('lerr').textContent = '';

  if (window.DEMO_MODE) {
    window.NODES = window.DEMO_NODES;
    window.NODE_TRAFFIC = window.DEMO_NODES.map(function(n) {
      var used = Number(n.traffic_used_gb || 0);
      var limit = n.traffic_limit_gb != null ? Number(n.traffic_limit_gb) : null;
      return {
        node_id: n.id, node_name: n.name, node_status: n.status,
        traffic_limit_gb: limit, traffic_used_gb: used,
        usage_ratio: limit ? used / limit : null,
        cycle_started_at: n.registered_at, cycle_ends_at: null,
        traffic_suspended_at: limit && used >= limit ? new Date().toISOString() : null,
        traffic_suspension_reason: limit && used >= limit ? 'traffic_limit_exceeded' : null,
      };
    });
    window.LINKS = window.DEMO_LINKS;
    window.JOBS = window.DEMO_JOBS;
    window.POLICIES = window.DEMO_POLICIES;
    window.DNS_P = window.DEMO_DNS;
    window.GEO_P = [];
    window.BALANCERS = [];
    window.GRAPH_DATA = window.DEMO_GRAPH;
    window.REGISTRATIONS = window.DEMO_REGISTRATIONS;
    window.PEERS = window.DEMO_PEERS;
    window.renderPeers?.();
    window.updatePeersBadge?.();
    window.renderNodes?.(); window.renderNodeTraffic?.(); window.renderLinks?.();
    window.renderPolicies?.(); window.renderJobs?.(); window.renderAudit?.(); window.renderElog?.();
    window.renderRegistrations?.(); window.updateRegBadge?.(); window.updateShellCounters?.();
    setTimeout(function() { window.drawTopo?.(); }, 60);
    window.pushEv?.('system.connected', 'DEMO MODE — not connected to real backend');
    window.startDemoMetricsTicker?.();
    window.scheduleLocaleRefresh?.();
    return;
  }

  try { await window.refreshHealth?.(); }
  catch (err) { window.pushEv?.('system.error', 'initial health load failed: ' + String(err && err.message ? err.message : err)); }
  try { await window.loadData(); }
  catch (err) { window.pushEv?.('system.error', 'initial data load failed: ' + String(err && err.message ? err.message : err)); }

  window.startHealthPolling();
  window.startFailbanPolling?.();
  window.startJobsTicker?.();
  window.refreshFailban?.().catch(function() {});
  window.connectWS?.();
  setTimeout(function() { window.drawTopo?.(); }, 60);
  window.scheduleLocaleRefresh?.();
};

// ── Event listeners (DOM-ready) ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Login form
  document.getElementById('lbtn').addEventListener('click', window.doLogin);
  document.getElementById('ip').addEventListener('keydown', function(e) {
    if (e.key === 'Enter') window.doLogin();
  });

  // Logout
  document.getElementById('logoutBtn').addEventListener('click', async function() {
    if (confirm(window.LANG === 'ru' ? 'Выйти из панели управления ONyX?' : 'Logout from ONyX Control Plane?')) {
      try { await window.apiFetch(window.API_PREFIX + '/auth/logout', { method: 'POST', redirectOn401: false }); } catch (_) {}
      window.authRedirect('');
    }
  });

  // Modal overlay click-to-close
  var _modalMdOnOverlay = false;
  document.getElementById('modalClose').addEventListener('click', window.closeModal);
  document.getElementById('modal').addEventListener('mousedown', function(event) {
    _modalMdOnOverlay = !!(event.target && event.target.id === 'modal');
  });
  document.getElementById('modal').addEventListener('click', function(event) {
    if (_modalMdOnOverlay && event.target && event.target.id === 'modal') window.closeModal();
    _modalMdOnOverlay = false;
  });

  // Detail panel click-outside-to-close
  document.addEventListener('mousedown', function(event) {
    var dp = document.getElementById('dp');
    if (!dp || !dp.classList.contains('open')) return;
    if (dp.contains(event.target)) return;
    window.closeDP();
  }, true);

  // Theme init
  try { var t = localStorage.getItem('onyx-theme'); if (t) window.setTheme(t); } catch (e) {}

  // Lang init
  try {
    var savedLang = localStorage.getItem('onyx-lang');
    if (savedLang === 'ru' || savedLang === 'en') window.LANG = savedLang;
  } catch (e) {}
  document.querySelectorAll('.lang-btn').forEach(function(b) {
    b.classList.toggle('active', b.textContent.trim().toLowerCase() === window.LANG);
  });
  window.scheduleLocaleRefresh?.();

  // MutationObserver for i18n refresh
  var app = document.getElementById('appWrap');
  if (app && typeof MutationObserver !== 'undefined') {
    var obs = new MutationObserver(function(mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].type === 'childList') { window.scheduleLocaleRefresh?.(); break; }
      }
    });
    obs.observe(app, { childList: true, subtree: true });
  }

  // ── "Add" button wiring (lost in Vite migration) ──────────────────────────
  var _btn = function(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
  _btn('btnAddNode',                 function(){ window.openNodeModal?.(); });
  _btn('btnAddLink',                 function(){ window.openLinkModal?.(); });
  _btn('btnAddRoutePolicy',          function(){ window.openRoutePolicyModal?.(); });
  _btn('btnAddDNSPolicy',            function(){ window.openDNSPolicyModal?.(); });
  _btn('btnAddGeoPolicy',            function(){ window.openGeoPolicyModal?.(); });
  _btn('btnAddBalancer',             function(){ window.openBalancerModal?.(); });
  _btn('btnAddUser',                 function(){ window.openUserModal?.(); });
  _btn('btnAddPlan',                 function(){ window.openPlanModal?.(); });
  _btn('btnAddTransportPackage',     function(){ window.openTransportPackageModal?.(); });
  _btn('btnAddXrayService',          function(){ window.openXrayServiceModal?.(); });
  _btn('btnAddTransitPolicy',        function(){ window.openTransitPolicyModal?.(); });
  _btn('btnAddAwgService',           function(){ window.openAwgServiceModal?.(); });
  _btn('btnAddWgService',            function(){ window.openWgServiceModal?.(); });
  _btn('btnAddOpenvpnCloakService',  function(){ window.openOpenvpnCloakServiceModal?.(); });
  _btn('btnCreateReferralPool',      function(){ window.openReferralPoolModal?.(); });

  // Auto-login check
  (async function init() {
    if (window.DEMO_MODE) { window.authRedirect(''); return; }
    var me = null;
    try {
      me = await window.apiFetch(window.API_PREFIX + '/auth/me', { redirectOn401: false });
    } catch (_) {
      window.authRedirect('');
      return;
    }
    try {
      await window.bootApp(me);
    } catch (err) {
      window.isAuthenticated = true;
      document.getElementById('loginWrap').style.display = 'none';
      document.getElementById('appWrap').style.display = 'flex';
      window.pushEv?.('system.error', 'boot failed: ' + String(err && err.message ? err.message : err));
      window.scheduleLocaleRefresh?.();
    }
  })();
});
