// Page module - all functions exposed as window globals

window.renderAudit = function renderAudit(){
  document.getElementById('alog').innerHTML = AUDIT_EVTS.map(function(e){
    return '<div class="eline">'
      +'<span class="et">'+esc(e.t)+'</span>'
      +'<span class="ety '+esc(e.cls)+'">'+esc(e.type)+'</span>'
      +'<span style="color:var(--t1);">'+esc(e.msg)+'</span>'
      +'</div>';
  }).join('');
};

window.renderElog = function renderElog(){
  var log = document.getElementById('elog');
  log.innerHTML = AUDIT_EVTS.slice().reverse().map(function(e){
    return '<div class="eline">'
      +'<span class="et">'+esc(e.t)+'</span>'
      +'<span class="ety '+esc(e.cls)+'">'+esc(e.type)+'</span>'
      +'<span style="color:var(--t1);">'+esc(e.msg)+'</span>'
      +'</div>';
  }).join('');
  log.scrollTop = log.scrollHeight;
};

window.refreshAudit = async function refreshAudit(){
  var events = await apiFetch(API_PREFIX + '/audit-logs?limit=50');
  AUDIT_EVTS = (events || []).map(function(evt){
    return {
      t: fmtDateTime(evt.created_at),
      type: evt.entity_type === 'job' ? 'job.event' : 'audit.event',
      cls: evt.level === 'error' ? 'err' : evt.entity_type === 'job' ? 'job' : 'aud',
      msg: evt.message || evt.entity_type
    };
  });
  renderAudit();
  renderElog();
};

export {};
