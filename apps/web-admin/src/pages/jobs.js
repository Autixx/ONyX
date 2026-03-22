// Page module - all functions exposed as window globals

window.isJobForceCancelable = function isJobForceCancelable(job){
  if(!job || job.state !== 'running' || !job.lease_expires_at) return false;
  var leaseMs = new Date(job.lease_expires_at).getTime();
  return !isNaN(leaseMs) && leaseMs < Date.now();
};

window.isJobRemoteAbortable = function isJobRemoteAbortable(job){
  return !!job && job.state === 'running' && job.tt === 'node' && (job.kind === 'bootstrap' || job.kind === 'discover');
};

window.isJobTargetReleasable = function isJobTargetReleasable(job){
  return !!job && job.tt === 'node' && (job.state === 'pending' || job.state === 'running');
};

window.fmtDurationSeconds = function fmtDurationSeconds(totalSeconds){
  var sec = Math.max(0, Math.floor(Number(totalSeconds) || 0));
  var h = Math.floor(sec / 3600);
  var m = Math.floor((sec % 3600) / 60);
  var s = sec % 60;
  if(h > 0) return h + 'h ' + String(m).padStart(2,'0') + 'm ' + String(s).padStart(2,'0') + 's';
  return m + 'm ' + String(s).padStart(2,'0') + 's';
};

window.jobAgeText = function jobAgeText(job){
  if(!job || !job.created_at) return '-';
  var created = new Date(job.created_at).getTime();
  if(isNaN(created)) return '-';
  var terminalStates = {succeeded:true, failed:true, dead:true, cancelled:true, rolled_back:true};
  if(terminalStates[job.state]){
    var endTs = null;
    if(job.finished_at){
      endTs = new Date(job.finished_at).getTime();
    }else if(job.cancelled_at){
      endTs = new Date(job.cancelled_at).getTime();
    }
    if(endTs != null && !isNaN(endTs)){
      var startTs = job.started_at ? new Date(job.started_at).getTime() : created;
      if(!isNaN(startTs)){
        return fmtDurationSeconds(Math.max(0, (endTs - startTs) / 1000));
      }
      return fmtDurationSeconds(Math.max(0, (endTs - created) / 1000));
    }
  }
  return fmtDurationSeconds((Date.now() - created) / 1000);
};

window.jobLeaseText = function jobLeaseText(job){
  if(!job) return '-';
  if(job.state !== 'running') return '-';
  if(!job.lease_expires_at) return 'no lease';
  var lease = new Date(job.lease_expires_at).getTime();
  if(isNaN(lease)) return '-';
  var delta = Math.floor((lease - Date.now()) / 1000);
  if(delta < 0) return 'stale ' + fmtDurationSeconds(Math.abs(delta));
  return 'in ' + fmtDurationSeconds(delta);
};

window.renderJobs = function renderJobs(){
  document.getElementById('jtb').innerHTML = JOBS.map(function(j){
    var actions = '';
    if(j.state === 'pending' || j.state === 'running'){
      actions += '<button class="btn sm red" onclick="event.stopPropagation();actionJobCancel(\''+esc(j.id)+'\')">CANCEL</button>';
    }
    if(isJobRemoteAbortable(j)){
      actions += '<button class="btn sm red" onclick="event.stopPropagation();actionJobAbortRemote(\''+esc(j.id)+'\')">ABORT REMOTE</button>';
    }
    if(isJobForceCancelable(j)){
      actions += '<button class="btn sm red" onclick="event.stopPropagation();actionJobForceCancel(\''+esc(j.id)+'\')">MARK CANCELLED</button>';
    }
    if(isJobTargetReleasable(j)){
      actions += '<button class="btn sm red" onclick="event.stopPropagation();actionJobReleaseTarget(\''+esc(j.id)+'\')">RELEASE TARGET</button>';
    }
    if(j.state === 'failed' || j.state === 'dead' || j.state === 'cancelled'){
      actions += '<button class="btn sm red" onclick="event.stopPropagation();actionJobRetry(\''+esc(j.id)+'\')">RETRY</button>';
    }
    return '<tr onclick="showJob(\''+esc(j.id)+'\')">'
      +'<td style="color:var(--t2);font-size:13px;">'+esc(j.id)+'</td>'
      +'<td class="m">'+esc(j.kind)+'</td>'
      +'<td style="font-size:13px;color:var(--t1);">'+esc(j.tt+':'+j.ti)+'</td>'
      +'<td>'+sp(j.state)+'</td>'
      +'<td style="color:var(--t2);">'+esc(j.ts)+'</td>'
      +'<td style="color:var(--t1);">'+esc(jobAgeText(j))+'</td>'
      +'<td style="color:var(--t1);">'+esc(jobLeaseText(j))+'</td>'
      +'<td style="display:flex;gap:5px;">'+actions+'</td>'
      +'</tr>';
  }).join('');
};

window.showJob = function showJob(id){
  var j = jobById(id); if(!j) return;
  JOB_DETAIL_SELECTED_ID = j.id;
  var previousLog = null;
  var previousScrollTop = 0;
  if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', j.id)){
    previousLog = document.querySelector('#dpb .jlog');
    if(previousLog){ previousScrollTop = previousLog.scrollTop; }
  }
  var events = (JOB_EVENTS[j.id] || []).slice().sort(function(a, b){
    var at = a && a.created_at ? new Date(a.created_at).getTime() : 0;
    var bt = b && b.created_at ? new Date(b.created_at).getTime() : 0;
    return bt - at;
  });
  var logHtml = events.length ? events.map(function(ev){
    var level = String(ev.level || 'info').toUpperCase();
    var msg = ev.message || '';
    var c = ev.level === 'error' ? 'er' : ev.level === 'warning' ? 'inf' : 'ok';
    var ts = ev.created_at ? fmtDateTime(ev.created_at) : '-';
    return '<div class="eline">'
      +'<span class="et">'+esc(ts)+'</span>'
      +'<span class="ety '+esc(c)+'">['+esc(level)+']</span>'
      +'<span style="color:var(--t1);">'+esc(msg)+'</span>'
      +'</div>';
  }).join('') : '<div class="inf">No job events loaded.</div>';
  var actions = '';
  if(j.state === 'pending' || j.state === 'running'){
    actions += '<button class="btn red" onclick="actionJobCancel(\''+esc(j.id)+'\')">CANCEL</button>';
  }
  if(isJobRemoteAbortable(j)){
    actions += '<button class="btn red" onclick="actionJobAbortRemote(\''+esc(j.id)+'\')">ABORT REMOTE</button>';
  }
  if(isJobForceCancelable(j)){
    actions += '<button class="btn red" onclick="actionJobForceCancel(\''+esc(j.id)+'\')">MARK AS CANCELLED</button>';
  }
  if(isJobTargetReleasable(j)){
    actions += '<button class="btn red" onclick="actionJobReleaseTarget(\''+esc(j.id)+'\')">RELEASE TARGET</button>';
  }
  if(j.state === 'failed' || j.state === 'dead' || j.state === 'cancelled'){
    actions += '<button class="btn" onclick="actionJobRetry(\''+esc(j.id)+'\')">RETRY NOW</button>';
  }
  openDP(j.kind,
    rows([['ID',j.id],['Target',j.tt+':'+j.ti],['State',j.state],['Created',j.ts],['Worker',j.worker_owner || '-'],['Heartbeat',j.heartbeat_at ? fmtDateTime(j.heartbeat_at) : '-'],['Lease Expires',j.lease_expires_at ? fmtDateTime(j.lease_expires_at) : '-'],['Cancel Requested',j.cancel_requested ? 'yes' : 'no'],['Step',j.step || '-'],['Error',j.errorText || '-']])
    +(actions ? '<div class="dp-actions">'+actions+'</div>' : '')
    +'<div class="stitle">Execution Log</div>'
    +'<div class="jlog">'+logHtml+'</div>',
    { kind:'job', id:j.id }
  );
  var nextLog = document.querySelector('#dpb .jlog');
  if(nextLog && previousLog){
    nextLog.scrollTop = previousScrollTop;
  }else if(nextLog){
    nextLog.scrollTop = 0;
  }
};

window.refreshJobs = async function refreshJobs(){
  var jobs = await apiFetch(API_PREFIX + '/jobs');
  JOBS = (jobs || []).map(function(job){
    return {
      id: job.id,
      kind: job.kind,
      tt: job.target_type,
      ti: job.target_id,
      state: job.state,
      ts: fmtTime(job.created_at),
      step: job.current_step || '',
      errorText: job.error_text || '',
      created_at: job.created_at,
      started_at: job.started_at || null,
      finished_at: job.finished_at || null,
      cancelled_at: job.cancelled_at || null,
      lease_expires_at: job.lease_expires_at || null,
      heartbeat_at: job.heartbeat_at || null,
      cancel_requested: !!job.cancel_requested,
      worker_owner: job.worker_owner || ''
    };
  });
  await Promise.all(JOBS.slice(0, 20).map(async function(job){
    try{
      JOB_EVENTS[job.id] = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(job.id) + '/events');
    }catch(_){
      JOB_EVENTS[job.id] = [];
    }
  }));
  renderJobs();
  refreshOpenJobDetail();
};

window.refreshOpenJobDetail = function refreshOpenJobDetail(){
  if(!JOB_DETAIL_SELECTED_ID) return;
  if(!document.getElementById('dp').classList.contains('open')) return;
  if(!detailContextIs('job', JOB_DETAIL_SELECTED_ID)) return;
  if(!jobById(JOB_DETAIL_SELECTED_ID)) return;
  showJob(JOB_DETAIL_SELECTED_ID);
};

window.startJobsTicker = function startJobsTicker(){
  if(_jobsTicker) clearInterval(_jobsTicker);
  _jobsTicker = setInterval(function(){
    if(_currentPage === 'jobs'){ renderJobs(); }
    refreshOpenJobDetail();
  }, 1000);
};

window.actionJobCancel = async function actionJobCancel(jobId){
  try{
    var job = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(jobId) + '/cancel', { method:'POST', body:{} });
    pushEv('job.cancel.requested', 'cancel requested for ' + jobId);
    await refreshJobs();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', job.id)){ showJob(job.id); }
  }catch(err){
    pushEv('job.cancel.error', 'cancel failed for ' + jobId + ': ' + (err && err.message ? err.message : err));
  }
};

window.actionJobRetry = async function actionJobRetry(jobId){
  try{
    var job = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(jobId) + '/retry-now', { method:'POST', body:{} });
    pushEv('job.retry.requested', 'retry queued for ' + jobId);
    await refreshJobs();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', job.id)){ showJob(job.id); }
  }catch(err){
    pushEv('job.retry.error', 'retry failed for ' + jobId + ': ' + (err && err.message ? err.message : err));
  }
};

window.actionJobForceCancel = async function actionJobForceCancel(jobId){
  try{
    if(!confirm('Mark this stale running job as cancelled? This clears the stuck job state after lease timeout and does not kill remote execution already in progress.')) return;
    var job = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(jobId) + '/force-cancel', { method:'POST', body:{} });
    pushEv('job.force_cancel.requested', 'mark-cancelled requested for ' + jobId);
    await refreshJobs();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', job.id)){ showJob(job.id); }
  }catch(err){
    pushEv('job.force_cancel.error', 'force-cancel failed for ' + jobId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionJobAbortRemote = async function actionJobAbortRemote(jobId){
  try{
    if(!confirm('Send best-effort remote stop commands to the target node and mark this job as cancel-requested? This is intended for stuck node bootstrap/discover jobs.')) return;
    var job = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(jobId) + '/abort-remote', { method:'POST', body:{} });
    pushEv('job.abort_remote.requested', 'remote abort requested for ' + jobId);
    await refreshJobs();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', job.id)){ showJob(job.id); }
  }catch(err){
    pushEv('job.abort_remote.error', 'remote abort failed for ' + jobId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

window.actionJobReleaseTarget = async function actionJobReleaseTarget(jobId){
  try{
    if(!confirm('Release this job target and clear the blocking job state? This is an administrative override for stuck jobs. ONX will mark the job as cancelled and release its lock, but this does not guarantee remote execution was terminated.')) return;
    var job = await apiFetch(API_PREFIX + '/jobs/' + encodeURIComponent(jobId) + '/release-target', { method:'POST', body:{} });
    pushEv('job.release_target.requested', 'target release requested for ' + jobId);
    await refreshJobs();
    if(document.getElementById('dp').classList.contains('open') && detailContextIs('job', job.id)){ showJob(job.id); }
  }catch(err){
    pushEv('job.release_target.error', 'target release failed for ' + jobId + ': ' + (err && err.message ? err.message : err));
    alert(err && err.message ? err.message : err);
  }
};

export {
  renderJobs,
  showJob,
  refreshJobs,
  refreshOpenJobDetail,
  startJobsTicker,
  isJobForceCancelable,
  isJobRemoteAbortable,
  isJobTargetReleasable,
  fmtDurationSeconds,
  jobAgeText,
  jobLeaseText,
  actionJobCancel,
  actionJobRetry,
  actionJobForceCancel,
  actionJobAbortRemote,
  actionJobReleaseTarget
};
