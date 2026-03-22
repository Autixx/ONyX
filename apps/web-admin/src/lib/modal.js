// modal.js — Detail panel, modal dialog, toast, form helpers

window.DP_CONTEXT = {kind:null, id:null};

window.openDP = function openDP(title, html, meta){
  var dpt = document.getElementById('dpt');
  if(dpt && dpt.dataset && dpt.dataset.i18nOriginalText){ delete dpt.dataset.i18nOriginalText; }
  document.getElementById('dpt').textContent = title;
  document.getElementById('dpb').innerHTML = html;
  document.getElementById('dp').classList.add('open');
  if(meta && meta.kind){
    window.DP_CONTEXT.kind = meta.kind;
    window.DP_CONTEXT.id = meta.id || null;
    if(meta.kind === 'job'){
      window.JOB_DETAIL_SELECTED_ID = meta.id || null;
    }else{
      window.JOB_DETAIL_SELECTED_ID = null;
    }
  }else{
    window.DP_CONTEXT.kind = null;
    window.DP_CONTEXT.id = null;
    window.JOB_DETAIL_SELECTED_ID = null;
  }
};

window.closeDP = function closeDP(){
  document.getElementById('dp').classList.remove('open');
  var dpt = document.getElementById('dpt');
  if(dpt && dpt.dataset && dpt.dataset.i18nOriginalText){ delete dpt.dataset.i18nOriginalText; }
  if(window.DP_CONTEXT.kind === 'job'){
    window.JOB_DETAIL_SELECTED_ID = null;
  }
  window.DP_CONTEXT.kind = null;
  window.DP_CONTEXT.id = null;
};

window.detailContextIs = function detailContextIs(kind, id){
  return window.DP_CONTEXT.kind === kind && String(window.DP_CONTEXT.id || '') === String(id || '');
};

window.resetI18nCache = function resetI18nCache(root){
  if(!root) return;
  delete root.dataset.i18nOriginalText;
  delete root.dataset.i18nOriginalPlaceholder;
  delete root.dataset.i18nOriginalTitle;
  root.querySelectorAll('*').forEach(function(el){
    delete el.dataset.i18nOriginalText;
    delete el.dataset.i18nOriginalPlaceholder;
    delete el.dataset.i18nOriginalTitle;
  });
};

window.closeModal = function closeModal(){
  var modal = document.getElementById('modal');
  var title = document.getElementById('modalTitle');
  var body = document.getElementById('modalBody');
  var actions = document.getElementById('modalActions');
  modal.classList.remove('open');
  window.resetI18nCache(title);
  window.resetI18nCache(body);
  window.resetI18nCache(actions);
  title.textContent = '';
  body.innerHTML = '';
  actions.innerHTML = '';
};

window.openModal = function openModal(title, bodyHtml, options){
  var opts = options || {};
  var titleEl = document.getElementById('modalTitle');
  var bodyEl = document.getElementById('modalBody');
  var actions = document.getElementById('modalActions');
  window.resetI18nCache(titleEl);
  window.resetI18nCache(bodyEl);
  window.resetI18nCache(actions);
  titleEl.textContent = title;
  bodyEl.innerHTML = bodyHtml;
  actions.innerHTML = '';
  var buttons = opts.buttons || [];
  buttons.forEach(function(btn){
    var el = document.createElement('button');
    el.className = btn.className || 'btn';
    el.textContent = btn.label;
    el.type = 'button';
    el.addEventListener('click', btn.onClick);
    actions.appendChild(el);
  });
  document.getElementById('modal').classList.add('open');
  var focusSelector = opts.focusSelector || 'input, select, textarea';
  var target = document.querySelector('#modalBody ' + focusSelector);
  if(target){ target.focus(); }
  window.scheduleLocaleRefresh();
};

window.bindModalForm = function bindModalForm(formId, onSubmit){
  var form = document.getElementById(formId);
  if(!form){ return; }
  form.addEventListener('submit', function(event){
    event.preventDefault();
    onSubmit(new FormData(form));
  });
};

window.showToast = function showToast(message, level, title){
  var stack = document.getElementById('toastStack');
  if(!stack) return;
  var toast = document.createElement('div');
  toast.className = 'toast ' + (level || 'info');
  toast.innerHTML = '<div class="toast-title">' + window.esc(title || (level === 'error' ? 'Error' : level === 'success' ? 'Done' : 'Notice')) + '</div>'
    + '<div class="toast-msg">' + window.esc(message || '') + '</div>';
  stack.appendChild(toast);
  window.setTimeout(function(){
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(6px)';
  }, 3400);
  window.setTimeout(function(){
    if(toast.parentNode){ toast.parentNode.removeChild(toast); }
  }, 3800);
};

window.formInput = function formInput(label, name, value, extra){
  return '<div class="mf-row '+((extra && extra.full) ? 'full' : '')+'">'
    +'<label class="mf-label" for="'+window.esc(name)+'">'+window.esc(label)+'</label>'
    +'<input class="mf-input" id="'+window.esc(name)+'" name="'+window.esc(name)+'" value="'+window.esc(value || '')+'" '+(extra && extra.type ? 'type="'+window.esc(extra.type)+'"' : 'type="text"')+' '+(extra && extra.placeholder ? 'placeholder="'+window.esc(extra.placeholder)+'"' : '')+' '+(extra && extra.required ? 'required' : '')+' '+(extra && extra.readonly ? 'readonly' : '')+'>'
    +(extra && extra.help ? '<div class="mf-help">'+window.esc(extra.help)+'</div>' : '')
    +'</div>';
};

window.formSelect = function formSelect(label, name, value, options, extra){
  return '<div class="mf-row '+((extra && extra.full) ? 'full' : '')+'">'
    +'<label class="mf-label" for="'+window.esc(name)+'">'+window.esc(label)+'</label>'
    +'<select class="mf-select" id="'+window.esc(name)+'" name="'+window.esc(name)+'">'
    +options.map(function(opt){
      var optionValue = typeof opt === 'string' ? opt : opt.value;
      var optionLabel = typeof opt === 'string' ? opt : opt.label;
      return '<option value="'+window.esc(optionValue)+'" '+(String(optionValue)===String(value) ? 'selected' : '')+'>'+window.esc(optionLabel)+'</option>';
    }).join('')
    +'</select>'
    +(extra && extra.help ? '<div class="mf-help">'+window.esc(extra.help)+'</div>' : '')
    +'</div>';
};

window.formTextarea = function formTextarea(label, name, value, extra){
  return '<div class="mf-row '+((extra && extra.full !== false) ? 'full' : '')+'">'
    +'<label class="mf-label" for="'+window.esc(name)+'">'+window.esc(label)+'</label>'
    +'<textarea class="mf-textarea" id="'+window.esc(name)+'" name="'+window.esc(name)+'" '
      +(extra && extra.placeholder ? 'placeholder="'+window.esc(extra.placeholder)+'" ' : '')
      +(extra && extra.readonly ? 'readonly ' : '')
      +'>'+window.esc(value || '')+'</textarea>'
    +(extra && extra.help ? '<div class="mf-help">'+window.esc(extra.help)+'</div>' : '')
    +'</div>';
};

window.formCheckbox = function formCheckbox(label, name, checked, extra){
  return '<div class="mf-row '+((extra && extra.full) ? 'full' : '')+'">'
    +'<label class="mf-label">'+window.esc(label)+'</label>'
    +'<label style="display:flex;align-items:center;gap:8px;color:var(--t0);"><input type="checkbox" name="'+window.esc(name)+'" '+(checked ? 'checked' : '')+'> '+window.esc(extra && extra.caption ? extra.caption : 'Enabled')+'</label>'
    +(extra && extra.help ? '<div class="mf-help">'+window.esc(extra.help)+'</div>' : '')
    +'</div>';
};

window.splitLines = function splitLines(value){
  return String(value || '').split(/\r?\n/).map(function(x){ return x.trim(); }).filter(Boolean);
};

window.membersToText = function membersToText(members){
  return (members || []).map(function(member){
    return [member.interface_name || '', member.gateway || '', member.ping_target || '', member.weight || 1].join(',');
  }).join('\n');
};

window.parseMembers = function parseMembers(text){
  return window.splitLines(text).map(function(line){
    var parts = line.split(',').map(function(p){ return p.trim(); });
    return {
      interface_name: parts[0] || '',
      gateway: parts[1] || null,
      ping_target: parts[2] || null,
      weight: parts[3] ? Number(parts[3]) : 1
    };
  }).filter(function(member){ return member.interface_name; });
};

window.checked = function checked(fd, name){
  return fd.get(name) === 'on';
};

export var openDP            = window.openDP;
export var closeDP           = window.closeDP;
export var detailContextIs   = window.detailContextIs;
export var openModal         = window.openModal;
export var closeModal        = window.closeModal;
export var bindModalForm     = window.bindModalForm;
export var resetI18nCache    = window.resetI18nCache;
export var showToast         = window.showToast;
export var formInput         = window.formInput;
export var formSelect        = window.formSelect;
export var formTextarea      = window.formTextarea;
export var formCheckbox      = window.formCheckbox;
export var splitLines        = window.splitLines;
export var membersToText     = window.membersToText;
export var parseMembers      = window.parseMembers;
export var checked           = window.checked;
