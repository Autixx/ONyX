// Page module - all functions exposed as window globals

window.apiCall = async function apiCall(){
  var path = document.getElementById('ap').value;
  var method = document.getElementById('am').value;
  var el = document.getElementById('ar');
  el.style.color = 'var(--acc)';
  el.textContent = '// '+method+' '+path+'\n// Connecting to backend...';
  try{
    var body = undefined;
    if(method !== 'GET'){
      var rawBody = document.getElementById('ab').value.trim();
      body = rawBody ? rawBody : undefined;
    }
    var data = await apiFetch(path, {
      method: method,
      body: body,
      headers: body ? {'Content-Type':'application/json'} : {}
    });
    el.style.color = 'var(--grn)';
    el.textContent = JSON.stringify(data, null, 2);
  }catch(err){
    el.style.color = 'var(--red)';
    el.textContent = '// Error: ' + (err && err.message ? err.message : err);
  }
};

export {};
