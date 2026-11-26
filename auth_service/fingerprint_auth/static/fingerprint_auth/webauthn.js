(() => {
  const app = document.getElementById('app');
  const status = document.getElementById('status');
  const csrf = document.querySelector('meta[name="csrf-token"]').content;
  const endpoints = app.dataset;
  const show = value => { status.textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
  const decode = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(s.length / 4) * 4, '=')), c => c.charCodeAt(0));
  const encode = buf => {
    if (buf == null) return null;
    let s = '';
    for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  };
  function supported() {
    if (!window.isSecureContext || !window.PublicKeyCredential || !navigator.credentials) throw new Error('WebAuthn requiert un navigateur compatible, localhost ou HTTPS.');
  }
  function creation(o) {
    if (PublicKeyCredential.parseCreationOptionsFromJSON) return PublicKeyCredential.parseCreationOptionsFromJSON(o);
    return {...o, challenge:decode(o.challenge), user:{...o.user,id:decode(o.user.id)},
      excludeCredentials:(o.excludeCredentials || []).map(c=>({...c,id:decode(c.id)}))};
  }
  function assertion(o) {
    if (PublicKeyCredential.parseRequestOptionsFromJSON) return PublicKeyCredential.parseRequestOptionsFromJSON(o);
    return {...o, challenge:decode(o.challenge), allowCredentials:(o.allowCredentials || []).map(c=>({...c,id:decode(c.id)}))};
  }
  function serialize(c) {
    if (typeof c.toJSON === 'function') return c.toJSON();
    const r = c.response;
    const response = {clientDataJSON:encode(r.clientDataJSON)};
    if (r.attestationObject) {
      response.attestationObject = encode(r.attestationObject);
      if (r.getTransports) response.transports = r.getTransports();
    } else {
      response.authenticatorData = encode(r.authenticatorData);
      response.signature = encode(r.signature);
      response.userHandle = encode(r.userHandle);
    }
    return {id:c.id, rawId:encode(c.rawId), type:c.type, response,
      authenticatorAttachment:c.authenticatorAttachment || undefined,
      clientExtensionResults:c.getClientExtensionResults()};
  }
  async function api(url, method='POST', body={}) {
    const options = {method, credentials:'same-origin', headers:{'X-CSRFToken':csrf,'Accept':'application/json'}};
    if (method === 'POST') { options.headers['Content-Type']='application/json'; options.body=JSON.stringify(body); }
    const res = await fetch(url, options);
    if (res.status === 204) return {};
    const data = await res.json().catch(()=>({error:`HTTP ${res.status}`}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }
  function bind(id, fn) {
    const b = document.getElementById(id);
    if (!b) return;
    b.addEventListener('click', async () => {
      if (app.dataset.busy === 'true') return;
      app.dataset.busy='true'; b.disabled=true;
      try { await fn(); } catch(e) { show(`${e.name || 'Erreur'} : ${e.message}`); }
      finally { b.disabled=false; app.dataset.busy='false'; }
    });
  }
  bind('register', async () => {
    supported();
    if (!document.getElementById('consent').checked) throw new Error('Accepte le consentement avant de continuer.');
    await api(endpoints.consent,'POST',{accepted:true});
    const options=await api(endpoints.registerOptions);
    show('Confirme sur ton appareil…');
    const c=await navigator.credentials.create({publicKey:creation(options.publicKey)});
    if (!c) throw new Error('Enrôlement annulé.');
    show(await api(endpoints.registerVerify,'POST',{challengeId:options.challengeId,response:serialize(c)}));
  });
  bind('login', async () => {
    supported();
    const options=await api(endpoints.loginOptions);
    show('Choisis ta passkey et confirme…');
    const c=await navigator.credentials.get({publicKey:assertion(options.publicKey)});
    if (!c) throw new Error('Vérification annulée.');
    show(await api(endpoints.loginVerify,'POST',{challengeId:options.challengeId,response:serialize(c)}));
  });
  async function list() {
    const data=await api(endpoints.credentials,'GET');
    const ul=document.getElementById('credentials'); ul.replaceChildren();
    for (const c of data.credentials) {
      const li=document.createElement('li'); li.textContent=`Passkey ${c.id} — ${c.created_at} `;
      const button=document.createElement('button'); button.className='danger'; button.textContent='Révoquer';
      button.addEventListener('click',async()=>{
        if (!confirm('Révoquer cette passkey ?')) return;
        button.disabled=true;
        try { await api(`${endpoints.credentials}${c.id}/`,'DELETE'); await list(); show('Passkey révoquée côté serveur.'); }
        catch(e){ show(e.message); button.disabled=false; }
      });
      li.appendChild(button); ul.appendChild(li);
    }
    if (!data.credentials.length) ul.textContent='Aucune passkey.';
  }
  bind('list',list);
  bind('withdraw',async()=>{
    if (!confirm('Supprimer toutes les passkeys de ce compte ?')) return;
    await api(endpoints.consent,'DELETE'); await list(); show('Consentement retiré. Les passkeys serveur sont supprimées.');
  });
})();
