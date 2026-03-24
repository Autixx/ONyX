// Page module — Client Update configuration

var _cuTab = 'direct';
var _cuConfig = null;

window.cuOnPageShow = function cuOnPageShow() {
  cuRefresh();
};

window.cuRefresh = async function cuRefresh() {
  var content = document.getElementById('clientUpdateContent');
  if (content) { content.innerHTML = '<div style="color:var(--t2);padding:16px;">Loading\u2026</div>'; }
  try {
    _cuConfig = await apiFetch(API_PREFIX + '/admin/client-updates/config');
    _cuRender(_cuConfig);
  } catch (err) {
    if (content) {
      content.innerHTML = '<div style="color:var(--red);padding:16px;">Load failed: ' + esc(String(err && err.message ? err.message : err)) + '</div>';
    }
  }
};

window.cuSwitchTab = function cuSwitchTab(tab) {
  _cuTab = tab;
  ['direct', 'mirror'].forEach(function(t) {
    var btn  = document.getElementById('cuTabBtn_' + t);
    var pane = document.getElementById('cuPane_' + t);
    if (btn)  { btn.classList.toggle('active', t === tab); }
    if (pane) { pane.style.display = t === tab ? '' : 'none'; }
  });
};

function _cuRender(cfg) {
  var content = document.getElementById('clientUpdateContent');
  if (!content) return;

  // Status bar
  var modeLabel = cfg.mode === 'direct' ? 'Direct (hosted here)' : cfg.mode === 'mirror' ? 'Mirror (external)' : 'Disabled';
  var html = '<div class="sys-stat-card" style="margin-bottom:16px;padding:12px 18px;display:flex;gap:28px;flex-wrap:wrap;align-items:center;">';
  html += '<div><div style="color:var(--t2);font-size:11px;margin-bottom:2px;">MODE</div><div style="font-size:14px;font-weight:600;">' + esc(modeLabel) + '</div></div>';
  html += '<div><div style="color:var(--t2);font-size:11px;margin-bottom:2px;">PUBLISHED VERSION</div><div style="font-size:14px;font-weight:600;">' + esc(cfg.version || '\u2014') + '</div></div>';
  if (cfg.download_url) {
    html += '<div style="flex:1;min-width:120px;"><div style="color:var(--t2);font-size:11px;margin-bottom:2px;">DOWNLOAD URL</div>'
          + '<div style="font-size:12px;word-break:break-all;color:var(--acc);">' + esc(cfg.download_url) + '</div></div>';
  }
  if (cfg.version) {
    html += '<div><button class="btn sm red" onclick="cuClearUpdate()">DISABLE</button></div>';
  }
  html += '</div>';

  // Tabs
  html += '<div class="failban-sources" style="margin-bottom:16px;">'
        + '<button id="cuTabBtn_direct" class="failban-scope-tab' + (_cuTab === 'direct' ? ' active' : '') + '" onclick="cuSwitchTab(\'direct\')">Direct</button>'
        + '<button id="cuTabBtn_mirror" class="failban-scope-tab' + (_cuTab === 'mirror' ? ' active' : '') + '" onclick="cuSwitchTab(\'mirror\')">Mirror</button>'
        + '</div>';

  // Direct pane
  html += '<div id="cuPane_direct"' + (_cuTab !== 'direct' ? ' style="display:none"' : '') + '>';
  html += '<p style="color:var(--t2);font-size:13px;margin:0 0 14px;">Upload a .zip archive to this server. Clients download it from the panel\'s public URL.</p>';
  html += '<div style="display:flex;flex-direction:column;gap:10px;max-width:480px;">';
  html += '<label><span class="form-label">Version</span>'
        + '<input id="cuDirectVersion" class="finput" style="width:100%;box-sizing:border-box;" placeholder="e.g. 0.3.0" value="' + esc(cfg.mode === 'direct' ? cfg.version : '') + '"></label>';
  html += '<label><span class="form-label">Release notes</span>'
        + '<textarea id="cuDirectNotes" class="finput" style="width:100%;box-sizing:border-box;height:64px;resize:vertical;">' + esc(cfg.mode === 'direct' ? cfg.notes : '') + '</textarea></label>';
  html += '<label><span class="form-label">ZIP file</span>'
        + '<input id="cuDirectFile" type="file" accept=".zip" style="color:var(--t0);margin-top:4px;"></label>';
  if (cfg.mode === 'direct' && cfg.filename) {
    html += '<div style="color:var(--t2);font-size:12px;">Current file: <span style="color:var(--acc);">' + esc(cfg.filename) + '</span></div>';
  }
  html += '</div>';
  html += '<div style="margin-top:14px;"><button class="btn pri" onclick="cuUpload()">UPLOAD &amp; PUBLISH</button></div>';
  html += '<div id="cuDirectStatus" style="margin-top:10px;font-size:13px;min-height:18px;"></div>';
  html += '</div>';

  // Mirror pane
  html += '<div id="cuPane_mirror"' + (_cuTab !== 'mirror' ? ' style="display:none"' : '') + '>';
  html += '<p style="color:var(--t2);font-size:13px;margin:0 0 14px;">Specify an external .zip URL (S3, GitHub Releases, CDN, etc.).</p>';
  html += '<div style="display:flex;flex-direction:column;gap:10px;max-width:480px;">';
  html += '<label><span class="form-label">Version</span>'
        + '<input id="cuMirrorVersion" class="finput" style="width:100%;box-sizing:border-box;" placeholder="e.g. 0.3.0" value="' + esc(cfg.mode === 'mirror' ? cfg.version : '') + '"></label>';
  html += '<label><span class="form-label">ZIP URL</span>'
        + '<input id="cuMirrorUrl" class="finput" style="width:100%;box-sizing:border-box;" placeholder="https://example.com/ONyXClient.zip" value="' + esc(cfg.mirror_url || '') + '"></label>';
  html += '<label><span class="form-label">Release notes</span>'
        + '<textarea id="cuMirrorNotes" class="finput" style="width:100%;box-sizing:border-box;height:64px;resize:vertical;">' + esc(cfg.mode === 'mirror' ? cfg.notes : '') + '</textarea></label>';
  html += '</div>';
  html += '<div style="margin-top:14px;"><button class="btn pri" onclick="cuSaveMirror()">SAVE &amp; PUBLISH</button></div>';
  html += '<div id="cuMirrorStatus" style="margin-top:10px;font-size:13px;min-height:18px;"></div>';
  html += '</div>';

  content.innerHTML = html;
}

window.cuUpload = async function cuUpload() {
  var version   = String((document.getElementById('cuDirectVersion') || {}).value || '').trim();
  var notes     = String((document.getElementById('cuDirectNotes')   || {}).value || '').trim();
  var fileInput = document.getElementById('cuDirectFile');
  var statusEl  = document.getElementById('cuDirectStatus');

  if (!version) {
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'Version is required.'; }
    return;
  }
  if (!fileInput || !fileInput.files || !fileInput.files.length) {
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'Select a .zip file.'; }
    return;
  }

  var fd = new FormData();
  fd.append('file', fileInput.files[0]);

  if (statusEl) { statusEl.style.color = 'var(--t2)'; statusEl.textContent = 'Uploading\u2026'; }
  try {
    var url = API_PREFIX + '/admin/client-updates/upload?version=' + encodeURIComponent(version) + '&notes=' + encodeURIComponent(notes);
    var resp = await fetch(url, { method: 'POST', body: fd, credentials: 'include' });
    if (!resp.ok) {
      var e = await resp.json().catch(function() { return {}; });
      throw new Error(e.detail || resp.statusText);
    }
    _cuConfig = await resp.json();
    _cuTab = 'direct';
    _cuRender(_cuConfig);
    cuSwitchTab('direct');
    var s = document.getElementById('cuDirectStatus');
    if (s) { s.style.color = 'var(--grn)'; s.textContent = 'Published v' + _cuConfig.version + ' \u2014 ' + _cuConfig.download_url; }
  } catch (err) {
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'Error: ' + (err && err.message ? err.message : String(err)); }
  }
};

window.cuSaveMirror = async function cuSaveMirror() {
  var version   = String((document.getElementById('cuMirrorVersion') || {}).value || '').trim();
  var mirrorUrl = String((document.getElementById('cuMirrorUrl')     || {}).value || '').trim();
  var notes     = String((document.getElementById('cuMirrorNotes')   || {}).value || '').trim();
  var statusEl  = document.getElementById('cuMirrorStatus');

  if (!version)   { if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'Version is required.'; } return; }
  if (!mirrorUrl) { if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'URL is required.'; }     return; }

  try {
    _cuConfig = await apiFetch(API_PREFIX + '/admin/client-updates/config', {
      method: 'PATCH',
      body: { mode: 'mirror', version: version, notes: notes, mirror_url: mirrorUrl },
    });
    _cuTab = 'mirror';
    _cuRender(_cuConfig);
    cuSwitchTab('mirror');
    var s = document.getElementById('cuMirrorStatus');
    if (s) { s.style.color = 'var(--grn)'; s.textContent = 'Published v' + _cuConfig.version + '.'; }
  } catch (err) {
    if (statusEl) { statusEl.style.color = 'var(--red)'; statusEl.textContent = 'Error: ' + (err && err.message ? err.message : String(err)); }
  }
};

window.cuClearUpdate = async function cuClearUpdate() {
  if (!confirm('Disable client update? Clients will stop seeing the update prompt.')) return;
  try {
    _cuConfig = await apiFetch(API_PREFIX + '/admin/client-updates/config', {
      method: 'PATCH',
      body: { mode: '', version: '', notes: '', mirror_url: '' },
    });
    _cuRender(_cuConfig);
  } catch (err) {
    alert('Error: ' + (err && err.message ? err.message : String(err)));
  }
};

export {};
