// theme.js — Theme switcher

window.setTheme = function setTheme(name){
  var body = document.body;
  body.className = body.className.replace(/theme-\S+/g,'').trim();
  if(name) body.classList.add('theme-' + name);
  document.querySelectorAll('.theme-dot').forEach(function(d){
    d.classList.toggle('active', d.classList.contains('th-' + (name||'teal')));
  });
  try{ localStorage.setItem('onyx-theme', name); }catch(e){}
};

export var setTheme = window.setTheme;
