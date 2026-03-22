// Page module - all functions exposed as window globals

window._supportWs = null;
window._supportTicketId = null;
window._supportTypingTimer = null;
window._supportTypingThrottle = false;
window._supportTickets = {};
window._supportTicketsTimer = null;
window._supportUnread = {};   // ticketId → unread count

window._addSupportUnread = function _addSupportUnread(ticketId) {
  if (!ticketId) return;
  _supportUnread[ticketId] = (_supportUnread[ticketId] || 0) + 1;
  _updateSupportBadge();
};

window._clearSupportUnread = function _clearSupportUnread(ticketId) {
  if (!ticketId || !_supportUnread[ticketId]) return;
  delete _supportUnread[ticketId];
  _updateSupportBadge();
};

window._updateSupportBadge = function _updateSupportBadge() {
  var total = 0;
  Object.keys(_supportUnread).forEach(function(k){ total += _supportUnread[k]; });

  // Badge element (hidden span in DOM, cloned into sub-tab by switchGroup)
  var badge = document.getElementById('supportBadge');
  if (badge) { badge.textContent = String(total); badge.style.display = total > 0 ? '' : 'none'; }
  var badgeSub = document.getElementById('supportBadge_sub');
  if (badgeSub) { badgeSub.textContent = String(total); badgeSub.style.display = total > 0 ? '' : 'none'; }

  // Red dot on "Debug" main group tab
  var debugTab = document.querySelector('.nav-group-tab[data-g="debug"]');
  if (debugTab) {
    var dot = debugTab.querySelector('.support-unread-dot');
    if (total > 0 && !dot) {
      dot = document.createElement('span');
      dot.className = 'support-unread-dot';
      dot.style.cssText = 'width:6px;height:6px;border-radius:50%;background:var(--red);display:inline-block;margin-left:4px;vertical-align:middle;';
      debugTab.appendChild(dot);
    } else if (total === 0 && dot) {
      dot.remove();
    }
  }

  // Sidebar badges per ticket
  Object.keys(_supportUnread).forEach(function(tid) {
    var card = document.querySelector('.ticket-user-item[data-tid="' + tid + '"]');
    if (!card) return;
    var badge = card.querySelector('.ticket-unread-badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'ticket-unread-badge';
      badge.style.cssText = 'float:right;background:var(--red);color:#fff;border-radius:10px;padding:0 5px;font-size:11px;font-weight:bold;margin-top:1px;';
      card.appendChild(badge);
    }
    badge.textContent = String(_supportUnread[tid]);
  });
};

window._renderTicketChatHeader = function _renderTicketChatHeader(ticket) {
  var hdr = document.getElementById('ticketsChatHeader');
  if (!hdr) return;
  var displayName = ticket.username || (ticket.user_id ? ticket.user_id.slice(0, 12) : '?');
  var st = ticket.status || 'pending';
  var stColors = {pending:'var(--amb)',in_progress:'var(--acc)',resolved:'var(--grn)',rejected:'var(--red)'};
  var stLabels = {pending:'PENDING',in_progress:'IN PROGRESS',resolved:'RESOLVED',rejected:'REJECTED'};
  var stBadge = '<span id="ticketStatusBadge" style="font-size:11px;font-weight:400;color:' + (stColors[st]||'var(--t2)') + ';border:1px solid ' + (stColors[st]||'var(--t2)') + ';border-radius:2px;padding:0 5px;">' + (stLabels[st]||st.toUpperCase()) + '</span>';
  var canClose = (st === 'pending' || st === 'in_progress');
  var canDelete = (st === 'resolved' || st === 'rejected');
  hdr.innerHTML =
    '<span>' + esc(ticket.issue_type.toUpperCase()) + '</span>'
    + ' <span style="color:var(--t2);font-weight:400;font-size:12px;">' + esc(displayName) + '</span>'
    + ' ' + stBadge
    + ' <span id="clientStatusDot" style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--t2);vertical-align:middle;" title="Connecting…"></span>'
    + ' <span style="margin-left:auto;display:flex;gap:6px;align-items:center;">'
    + (canClose ? '<button class="btn" style="padding:2px 10px;font-size:12px;color:var(--grn);border-color:rgba(0,200,100,.35);" onclick="resolveTicket(\'' + esc(ticket.id) + '\')">RESOLVE</button>' : '')
    + (canClose ? '<button class="btn" style="padding:2px 10px;font-size:12px;color:var(--red);border-color:rgba(255,69,96,.35);" onclick="rejectTicket(\'' + esc(ticket.id) + '\')">REJECT</button>' : '')
    + (canDelete ? '<button class="btn" style="padding:2px 10px;font-size:12px;color:var(--red);border-color:rgba(255,69,96,.35);" onclick="deleteSupportTicket(\'' + esc(ticket.id) + '\')">DELETE</button>' : '')
    + '</span>';
};

window.resolveTicket = function resolveTicket(ticketId) {
  if (!confirm('Mark this ticket as Resolved?')) return;
  apiFetch(API_PREFIX + '/admin/support/' + ticketId + '/status', {method:'PATCH', body: JSON.stringify({status:'resolved'})}).then(function(data) {
    if (_supportTickets[ticketId]) { _supportTickets[ticketId].status = 'resolved'; _renderTicketChatHeader(_supportTickets[ticketId]); }
    loadSupportTickets(true);
    showToast('Ticket resolved', 'ok');
  }).catch(function(e) { showToast('Failed: ' + e, 'err'); });
};

window.rejectTicket = function rejectTicket(ticketId) {
  if (!confirm('Mark this ticket as Rejected?')) return;
  apiFetch(API_PREFIX + '/admin/support/' + ticketId + '/status', {method:'PATCH', body: JSON.stringify({status:'rejected'})}).then(function(data) {
    if (_supportTickets[ticketId]) { _supportTickets[ticketId].status = 'rejected'; _renderTicketChatHeader(_supportTickets[ticketId]); }
    loadSupportTickets(true);
    showToast('Ticket rejected', 'ok');
  }).catch(function(e) { showToast('Failed: ' + e, 'err'); });
};

window.loadSupportTickets = function loadSupportTickets(silent) {
  var sidebar = document.getElementById('ticketsSidebar');
  if (!sidebar) return;
  if (!silent) {
    sidebar.innerHTML = '<div style="padding:12px;color:var(--t2);font-size:13px;">Loading…</div>';
  }
  apiFetch(API_PREFIX + '/admin/support-tickets?limit=200').then(function(data) {
    _supportTickets = {};
    if (!data || !data.length) {
      sidebar.innerHTML = '<div style="padding:12px;color:var(--t2);font-size:13px;">No tickets</div>';
      return;
    }
    data.forEach(function(t) { _supportTickets[t.id] = t; });
    var prevActive = _supportTicketId;
    sidebar.innerHTML = data.map(function(t) {
      var dt = t.created_at ? new Date(t.created_at).toLocaleString() : '';
      var name = t.username || (t.user_id ? t.user_id.slice(0, 12) : '?');
      var isActive = t.id === prevActive ? ' active' : '';
      var stColors = {pending:'var(--amb)',in_progress:'var(--acc)',resolved:'var(--grn)',rejected:'var(--red)'};
      var stLabels = {pending:'PENDING',in_progress:'IN PROGRESS',resolved:'RESOLVED',rejected:'REJECTED'};
      var st = t.status || 'pending';
      var badge = '<span style="font-size:10px;color:' + (stColors[st]||'var(--t2)') + ';border:1px solid ' + (stColors[st]||'var(--t2)') + ';border-radius:2px;padding:0 3px;margin-left:4px;">' + (stLabels[st]||st.toUpperCase()) + '</span>';
      return '<div class="ticket-user-item' + isActive + '" onclick="selectSupportTicket(this,\'' + esc(t.id) + '\')" data-tid="' + esc(t.id) + '">'
        + '<div class="ticket-user-name">' + esc(name) + badge + '</div>'
        + '<div class="ticket-user-meta">' + esc(t.issue_type) + ' · ' + esc(dt) + '</div>'
        + '</div>';
    }).join('');
  }).catch(function() {
    if (!silent) {
      sidebar.innerHTML = '<div style="padding:12px;color:var(--t2);font-size:13px;">Failed to load</div>';
    }
  });
};

window.startSupportTicketsRefresh = function startSupportTicketsRefresh() {
  stopSupportTicketsRefresh();
  _supportTicketsTimer = setInterval(function() {
    loadSupportTickets(true);
  }, 10000);
};

window.stopSupportTicketsRefresh = function stopSupportTicketsRefresh() {
  if (_supportTicketsTimer) { clearInterval(_supportTicketsTimer); _supportTicketsTimer = null; }
};

window.selectSupportTicket = function selectSupportTicket(el, ticketId) {
  var ticket = _supportTickets[ticketId];
  if (!ticket) return;
  document.querySelectorAll('.ticket-user-item').forEach(function(i) { i.classList.remove('active'); });
  el.classList.add('active');
  _clearSupportUnread(ticketId);
  if (_supportWs) { _supportWs.close(); _supportWs = null; }
  _supportTicketId = ticket.id;
  var displayName = ticket.username || (ticket.user_id ? ticket.user_id.slice(0, 12) : '?');
  _renderTicketChatHeader(ticket);
  document.getElementById('ticketsChatHeader').querySelector && void(0);
  var box = document.getElementById('ticketsMessages');
  box.innerHTML = '<div style="color:var(--t2);font-size:13px;text-align:center;padding:20px;">Connecting…</div>';
  document.getElementById('ticketTypingIndicator').style.display = 'none';
  var wsBase = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + API_PREFIX;
  var ws = new WebSocket(wsBase + '/ws/admin/support/' + ticket.id);
  _supportWs = ws;
  ws.onopen = function() {
    var dot = document.getElementById('clientStatusDot');
    if (dot) { dot.style.background = 'var(--amb)'; dot.title = 'WS connected, waiting for client…'; }
  };
  ws.onmessage = function(ev) {
    var frame; try { frame = JSON.parse(ev.data); } catch(e) { return; }
    _handleSupportFrame(frame);
  };
  ws.onclose = function() {
    if (_supportWs === ws) _supportWs = null;
    var dot = document.getElementById('clientStatusDot');
    if (dot) { dot.style.background = 'var(--t2)'; dot.title = 'Disconnected'; }
  };
  ws.onerror = function() {
    var b = document.getElementById('ticketsMessages');
    if (b) b.innerHTML += '<div style="color:var(--t2);font-size:13px;text-align:center;padding:8px;">Connection error</div>';
  };
};

window.deleteSupportTicket = function deleteSupportTicket(ticketId) {
  if (!confirm('Delete this ticket and all its messages?')) return;
  apiFetch(API_PREFIX + '/admin/support/' + ticketId, {method: 'DELETE'}).then(function() {
    if (_supportWs) { _supportWs.close(); _supportWs = null; }
    _supportTicketId = null;
    document.getElementById('ticketsChatHeader').innerHTML = '<span style="color:var(--t2);">Select a ticket</span>';
    document.getElementById('ticketsMessages').innerHTML = '<div class="tickets-empty">Select a ticket from the list</div>';
    document.getElementById('ticketTypingIndicator').style.display = 'none';
    loadSupportTickets();
    showToast('Ticket deleted', 'ok');
  }).catch(function(e) {
    showToast('Delete failed: ' + e, 'err');
  });
};

window._handleSupportFrame = function _handleSupportFrame(frame) {
  var box = document.getElementById('ticketsMessages');
  var typInd = document.getElementById('ticketTypingIndicator');
  if (!box) return;
  if (frame.type === 'system.connected') {
    box.innerHTML = '';
    var hist = frame.history || [];
    if (!hist.length) {
      box.innerHTML = '<div class="tickets-empty" style="flex:none;padding:20px 0;">No messages yet</div>';
    }
    hist.forEach(function(m) { _appendSupportMsg(box, m); });
    box.scrollTop = box.scrollHeight;
  } else if (frame.type === 'message') {
    var empty = box.querySelector('.tickets-empty');
    if (empty) empty.remove();
    _appendSupportMsg(box, frame);
    box.scrollTop = box.scrollHeight;
    if (frame.sender !== 'agent' && _currentPage !== 'tickets') {
      _addSupportUnread(_supportTicketId);
    }
  } else if (frame.type === 'typing' && frame.sender === 'client') {
    if (typInd) {
      typInd.style.display = '';
      clearTimeout(_supportTypingTimer);
      _supportTypingTimer = setTimeout(function() { typInd.style.display = 'none'; }, 3000);
    }
  } else if (frame.type === 'system.client_online') {
    var dot = document.getElementById('clientStatusDot');
    if (dot) { dot.style.background = 'var(--grn)'; dot.title = 'Client online'; }
  } else if (frame.type === 'system.client_offline') {
    var dot = document.getElementById('clientStatusDot');
    if (dot) { dot.style.background = 'var(--amb)'; dot.title = 'Client offline'; }
  } else if (frame.type === 'system.status_changed') {
    var tid = frame.ticket_id;
    if (_supportTickets[tid]) {
      _supportTickets[tid].status = frame.status;
      if (tid === _supportTicketId) { _renderTicketChatHeader(_supportTickets[tid]); }
    }
    loadSupportTickets(true);
  } else if (frame.type === 'system.autoclose_warning') {
    var b2 = document.getElementById('ticketsMessages');
    if (b2) {
      b2.innerHTML += '<div style="color:var(--amb);font-size:12px;text-align:center;padding:6px;border:1px solid var(--amb);border-radius:4px;margin:4px 0;">⚠ This ticket will be auto-closed in ' + (frame.closes_in_hours||12) + ' hours due to inactivity.</div>';
      b2.scrollTop = b2.scrollHeight;
    }
  }
};

window._appendSupportMsg = function _appendSupportMsg(box, m) {
  var isAgent = m.sender === 'agent';
  var d = document.createElement('div');
  d.className = 'ticket-msg ' + (isAgent ? 'admin' : 'user');
  var timeStr = '';
  if (m.sent_at) { try { timeStr = new Date(m.sent_at).toLocaleTimeString(); } catch(e) {} }
  d.innerHTML = '<div>' + esc(m.text) + '</div>'
    + '<div class="ticket-msg-meta">' + (isAgent ? 'agent' : 'client') + (timeStr ? ' · ' + timeStr : '') + '</div>';
  box.appendChild(d);
};

window.sendSupportReply = function sendSupportReply() {
  var inp = document.getElementById('ticketReply');
  var txt = inp.value.trim();
  if (!txt) return;
  if (!_supportWs || _supportWs.readyState !== WebSocket.OPEN) {
    showToast('Not connected to ticket', 'warn');
    return;
  }
  _supportWs.send(JSON.stringify({type: 'message', text: txt}));
  inp.value = '';
};

window._onSupportReplyKey = function _onSupportReplyKey(e) {
  if (e.key === 'Enter') { sendSupportReply(); return; }
  if (!_supportWs || _supportWs.readyState !== WebSocket.OPEN) return;
  if (!_supportTypingThrottle) {
    _supportWs.send(JSON.stringify({type: 'typing'}));
    _supportTypingThrottle = true;
    setTimeout(function() { _supportTypingThrottle = false; }, 1000);
  }
};

window.updateOpenTicketCount = function updateOpenTicketCount() {
  apiFetch(API_PREFIX + '/admin/support-tickets?limit=500').then(function(data) {
    var count = 0;
    if (data && data.length) {
      count = data.filter(function(t){ return t.status === 'pending' || t.status === 'in_progress'; }).length;
    }
    var el = document.getElementById('sOpenTickets');
    if (!el) return;
    el.textContent = String(count);
    el.style.color = count > 0 ? 'var(--amb)' : 'var(--grn)';
    var card = document.getElementById('openTicketsCard');
    if (card) card.title = count > 0 ? (count + ' open ticket(s) — click to open Support Chat') : 'No open tickets';
  }).catch(function(){});
};

export {};
