// Teste da PWA num Chromium real (CDP) com uma API Google FALSA injetada.
// Nunca toca na Sheet verdadeira. Uso:  node tests/pwa_smoke.mjs [pasta-para-screenshots]
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SHOTS = process.argv[2] || path.join(ROOT, 'tests', '_shots');
mkdirSync(SHOTS, { recursive: true });
const HTTP = 8765, DBG = 9333;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

const server = spawn('python3', ['-m', 'http.server', String(HTTP), '--bind', '127.0.0.1', '--directory', ROOT], { stdio: 'ignore' });
const profile = path.join(homedir(), 'snap', 'chromium', 'common', `pwa-test-${process.pid}`);
const chrome = spawn(process.env.CHROMIUM || 'chromium', ['--headless=new', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
  `--remote-debugging-port=${DBG}`, `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
const cleanup = () => { try { chrome.kill('SIGKILL'); } catch { } try { server.kill('SIGKILL'); } catch { } };
process.on('exit', cleanup);

async function until(fn, ms = 15000, step = 150) { const t0 = Date.now(); for (;;) { try { const v = await fn(); if (v) return v; } catch { } if (Date.now() - t0 > ms) return null; await sleep(step); } }

const results = []; const problems = [];
const check = (name, ok, detail = '') => { results.push({ name, ok }); console.log(`${ok ? '  ok ' : ' FAIL'}  ${name}${!ok && detail ? '  -> ' + detail : ''}`); };

// ---- API Google falsa (corre no browser antes do código da app) ----
const FAKE = `(() => {
  const TZ='Europe/Lisbon', pad=n=>String(n).padStart(2,'0');
  const today=()=>new Intl.DateTimeFormat('en-CA',{timeZone:TZ}).format(new Date());
  const U=iso=>{const [y,m,d]=iso.split('-').map(Number);return Date.UTC(y,m-1,d)};
  const add=(iso,n)=>{const t=new Date(U(iso)+n*864e5);return t.getUTCFullYear()+'-'+pad(t.getUTCMonth()+1)+'-'+pad(t.getUTCDate())};
  const mon=iso=>{const d=new Date(U(iso)).getUTCDay();return add(iso,d===0?-6:1-d)};
  const serial=iso=>Math.round((U(iso)-Date.UTC(1899,11,30))/864e5);
  const t0=today(), m0=mon(t0), when=(iso,hm)=>iso+'T'+hm+':12.345+01:00';
  const state={
    passe:[serial(add(t0,-9)),29,serial(add(t0,20)),20],
    weekly:[[add(m0,1),'Aveiro','Lisboa Oriente',524,'06:45',525,'18:30','SIM'],[add(m0,3),'Aveiro','Lisboa Oriente',524,'06:45',525,'18:30','SIM'],
            [add(m0,-6),'Aveiro','Lisboa Oriente',520,'07:27',521,'18:00','SIM']],
    tickets:[[add(t0,1),524,'Aveiro','Lisboa Oriente','06:45',3,42,'REF123'],[add(m0,-6),520,'Aveiro','Lisboa Oriente','07:27',5,11,'REF100']],
    logs:[[when(add(t0,-1),'06:39'),'PREFLIGHT','','','','','OK','',''],[when(add(t0,-1),'06:45'),'COMPRA',add(t0,0),'ida',524,200,'SALE_CREATED','','alvo 06:45:00.000 | enviado +3 ms'],
          [when(add(t0,-1),'06:45'),'COMPRA',add(t0,0),'ida',524,'','CONFIRMED','REF123',''],[when(add(t0,-2),'18:31'),'COMPRA',add(t0,-1),'volta',525,409,'SOLD_OUT','','Não há lugares.'],
          [when(add(t0,-2),'18:30'),'ERRO',add(t0,-1),'volta',525,'','FAILED','','Login na CP falhou: CAPTCHA']],
  };
  // chaves da CP falsas + uma CP falsa: o 524 parte do Porto às 06:10 e passa em Aveiro às 06:45
  localStorage.setItem('bilhetes_cp.cpkeys', JSON.stringify({t:'k',i:'i',s:'s'}));
  const TT={524:[{station:{code:'94-2006',designation:'Porto Campanha'},departure:'06:10'},{station:{code:'94-38000',designation:'Aveiro'},departure:'06:45'},{station:{code:'94-31039',designation:'Lisboa Oriente'},arrival:'09:52'}],
            525:[{station:{code:'94-31039',designation:'Lisboa Oriente'},departure:'18:30'},{station:{code:'94-38000',designation:'Aveiro'},arrival:'20:45'}]};
  const realFetch=window.fetch.bind(window);
  window.fetch=(u,o)=>{const m=String(u).match(/trains\\/(\\d+)\\/timetable\\//); if(m){const st=TT[m[1]]; return Promise.resolve(new Response(JSON.stringify(st?{trainStops:st}:{}),{status:st?200:404}));} return realFetch(u,o);};
  window.__STATE=state; window.__saved=null;
  window.__BCP_API={
    async load(){return {passe:state.passe,weeklyRaw:state.weekly.map(r=>[...r]),ticketsRaw:state.tickets.map(r=>[...r]),logsRaw:state.logs.map(r=>[...r])};},
    async saveWeek(weekStart,newRows){window.__saved={weekStart,newRows};state.weekly=window.__BCP.mergeWeek(state.weekly,weekStart,newRows);},
  };
})();`;

let ws, nextId = 1; const pending = new Map(); const listeners = [];
const send = (method, params = {}) => new Promise((res, rej) => { const id = nextId++; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })); });
const ev = async (expression) => { const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value; };
const shot = async (name) => { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(path.join(SHOTS, name + '.png'), Buffer.from(r.data, 'base64')); };
const click = (sel) => ev(`(()=>{const e=document.querySelector(${JSON.stringify(sel)}); if(!e) throw new Error('não existe: '+${JSON.stringify(sel)}); e.click(); return true;})()`);
const text = (sel) => ev(`(document.querySelector(${JSON.stringify(sel)})||{}).innerText||''`);
const load = async () => {
  for (let tentativa = 1; tentativa <= 2; tentativa++) {   // o Chromium (snap) às vezes arranca devagar
    await send('Page.navigate', { url: `http://127.0.0.1:${HTTP}/index.html` });
    if (await until(() => ev(`!!window.__BCP && !!document.querySelector('#view')?.children.length && !document.querySelector('#view .skel')`), 15000)) return;
  }
};

try {
  await until(async () => (await fetch(`http://127.0.0.1:${HTTP}/manifest.webmanifest`)).ok, 8000);
  await until(async () => (await fetch(`http://127.0.0.1:${DBG}/json/version`)).ok, 20000);
  const tab = await (await fetch(`http://127.0.0.1:${DBG}/json/new?about:blank`, { method: 'PUT' })).json();
  ws = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j; });
  ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); } else listeners.forEach(f => f(d)); };
  listeners.push((d) => {
    if (d.method === 'Runtime.exceptionThrown') problems.push('exceção: ' + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text));
    if (d.method === 'Log.entryAdded' && d.params.entry.level === 'error' && !/googleapis|gstatic|accounts\.google|apis\.google|workbox|ERR_(BLOCKED|INTERNET|NAME)/i.test(d.params.entry.url + d.params.entry.text)) problems.push('log: ' + d.params.entry.text + ' ' + (d.params.entry.url || ''));
  });
  for (const m of ['Page.enable', 'Runtime.enable', 'Log.enable', 'Network.enable']) await send(m);
  await send('Network.setBlockedURLs', { urls: ['*accounts.google.com*', '*apis.google.com*'] });   // não são precisos com a API falsa
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send('Emulation.setTouchEmulationEnabled', { enabled: true });
  await send('Page.addScriptToEvaluateOnNewDocument', { source: FAKE });

  console.log('\n== Carregamento');
  const consoleMsgs = [];
  listeners.push((d) => { if (d.method === 'Runtime.consoleAPICalled') consoleMsgs.push(d.params.type + ': ' + d.params.args.map(a => a.value ?? a.description).join(' ')); });
  await load();
  if (!(await ev('!!window.__BCP').catch(() => false))) {
    console.log('DIAGNÓSTICO: a app não arrancou.');
    console.log('  readyState:', await ev('document.readyState'), '| url:', await ev('location.href'));
    console.log('  texto da página:', JSON.stringify((await ev('document.body.innerText')).slice(0, 200)));
    console.log('  consola:', JSON.stringify(consoleMsgs.slice(0, 6)));
    console.log('  problemas:', JSON.stringify(problems.slice(0, 4)));
  }
  check('a app arranca e mostra conteúdo', await ev(`document.querySelector('#view').innerText.length>40`));
  check('título e versão', (await ev('document.title')) === 'Bilhetes CP' && (await ev('__BCP.VERSION')) === 'v1.1.1');
  check('sem scroll horizontal', await ev(`document.documentElement.scrollWidth<=innerWidth && document.querySelector('#view').scrollWidth<=document.querySelector('#view').clientWidth+1`));
  const home = await text('#view');
  check('ação em destaque: falta configurar a semana seguinte', /Falta configurar a semana de \d\d\/\d\d a \d\d\/\d\d/.test(home), home.slice(0, 80));
  check('mostra o próximo comboio como bilhete', /Próximo comboio/.test(home) && /Carruagem/.test(home) && /42/.test(home));
  check('mostra o passe com dias restantes', /Passe Verde/.test(home) && /20 dias/.test(home), (home.match(/\d+ dias?/) || [''])[0]);
  await shot('01-semana');

  console.log('\n== Separadores');
  await click('[data-tab="bilhetes"]'); const bil = await text('#view');
  check('Bilhetes: mostra os bilhetes com lugar e referência', /REF123/.test(bil) && /Anteriores/.test(bil) && /Próximos/.test(bil));
  await shot('02-bilhetes');
  await click('[data-tab="registo"]'); let reg = await text('#view');
  check('Registo: mostra os eventos em português', /Venda criada/.test(reg) && /Comprado/.test(reg) && /Login na CP falhou/.test(reg) && !/SALE_CREATED|CONFIRMED/.test(reg));
  await click('[data-f="bad"]'); reg = await text('#view');
  check('Registo: filtro "Problemas" só deixa esgotado/falhas', /Esgotado/.test(reg) && /Falhou/.test(reg) && !/Verificação/.test(reg) && !/Venda criada/.test(reg));
  await shot('03-registo');
  await click('[data-tab="semana"]');

  console.log('\n== Editor da semana');
  await click('.hero [data-act="edit-week"]');
  check('o editor abre na semana seguinte, vazia, com "Repetir a semana anterior"', (await ev(`!document.querySelector('#editor').hidden`)) && /Repetir a semana anterior/.test(await text('#editor')));
  await click('[data-act="copy-prev"]');
  const nDays = await ev(`document.querySelectorAll('#editor .dayc').length`);
  check('repetir a semana anterior copia os 2 dias da semana atual', nDays === 2, 'dias=' + nDays);
  const inWeek = await ev(`(()=>{const E=__BCP.S.editor,U=s=>{const[y,m,d]=s.split('-').map(Number);return Date.UTC(y,m-1,d)};return E.days.every(d=>U(d.date)>=U(E.week)&&U(d.date)<=U(E.week)+6*864e5)})()`);
  check('as datas copiadas caem na semana seguinte (+7 dias)', inWeek);
  check('mostra a hora da compra automática (T-24h)', /Compra automática/.test(await text('#editor')));
  await sleep(1000);
  const ft = await text('#editor');
  check('a data sugerida da compra segue a partida do comboio na 1.ª estação (Porto 06:10, não Aveiro 06:45)', /Compra automática [^\n]* às 06:10 \(partida em Porto Campanha\)/.test(ft), ft.match(/Compra automática[^\n]*/g)?.join(' | '));
  check('sem diferença (volta: 1.ª estação = embarque) não acrescenta nota', /Compra automática [^\n]* às 18:30(?! \()/.test(ft) && !/18:30 \(partida/.test(ft));
  // a hora da Config é a da 1.ª estação (caso do 520): aceita-se, confirma-se e mostra-se o embarque
  await ev(`(()=>{const i=document.querySelector('#editor .dayc [data-f="ida.time"]'); i.value='06:10'; i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await sleep(1200);
  const t1 = await text('#editor .dayc [data-tt="ida"]'), f1 = await text('#editor .dayc [data-fire="ida"]');
  check('hora da 1.ª estação (06:10) é aceite e confirmada pela CP', /Confirmado pela CP/.test(t1) && /Porto Campanha 06:10/.test(t1), t1);
  check('com a hora da 1.ª estação a compra é às 06:10 e mostra o embarque às 06:45', /às 06:10 · embarque às 06:45/.test(f1), f1);
  await ev(`(()=>{const i=document.querySelector('#editor .dayc [data-f="ida.time"]'); i.value='07:00'; i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await sleep(1200);
  const t2 = await text('#editor .dayc [data-tt="ida"]');
  check('uma hora que não é nem a da 1.ª estação nem a de embarque avisa e sugere a da 1.ª estação', /A CP indica 06:10 \(Porto Campanha\) e 06:45/.test(t2) && /Usar 06:10/.test(t2), t2);
  await ev(`(()=>{const i=document.querySelector('#editor .dayc [data-f="ida.time"]'); i.value='06:45'; i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  const noite = await ev(`(()=>{const a=__BCP.anchorFromStops([{station:{code:'A',designation:'Porto'},departure:'23:30'},{station:{code:'B'},departure:'01:10'}],'B','01:10','2026-09-22'); return a.startDate+' '+a.time})()`);
  check('comboio que passa a meia-noite antes do embarque parte na véspera', noite === '2026-09-21 23:30', noite);
  await shot('04-editor');

  // validação
  await ev(`(()=>{const i=document.querySelector('#editor .dayc [data-f="ida.train"]'); i.value='abc'; i.dispatchEvent(new Event('input',{bubbles:true}));})()`);
  await ev(`window.__saved=null`); await click('[data-act="save-week"]');
  check('não guarda com dados inválidos e explica o problema', (await ev('window.__saved')) === null && /inválido/.test(await text('#editor .errs:not(:empty)')));
  await shot('05-editor-erro');
  await ev(`(()=>{const i=document.querySelector('#editor .dayc [data-f="ida.train"]'); i.value='524'; i.dispatchEvent(new Event('input',{bubbles:true}));})()`);

  // teclado: com o teclado aberto o formulário e a barra de guardar têm de continuar visíveis
  console.log('\n== Teclado do telemóvel');
  await ev(`document.querySelector('#editor .dayc [data-f="volta.train"]').focus()`);
  await ev(`__BCP.applyViewport({height:430,offsetTop:0})`); await sleep(700);
  const kb = await ev(`(()=>{const app=document.querySelector('#app').getBoundingClientRect(), a=document.activeElement.getBoundingClientRect(), b=document.querySelector('#editor .savebar').getBoundingClientRect(), body=document.querySelector('#edBody').getBoundingClientRect();
    return {appH:Math.round(app.height), open:document.body.classList.contains('kb-open'), navHidden:getComputedStyle(document.querySelector('#tabs')).display==='none', saveBottom:Math.round(b.bottom), inputVisible:a.top>=body.top-1&&a.bottom<=body.bottom+1, inputTop:Math.round(a.top), inputBottom:Math.round(a.bottom), bodyTop:Math.round(body.top), bodyBottom:Math.round(body.bottom)}})()`);
  check('com o teclado, a app encolhe para o visual viewport (430px)', kb.appH === 430, JSON.stringify(kb));
  check('com o teclado, a barra de navegação sai do caminho', kb.open && kb.navHidden);
  check('com o teclado, o botão Guardar fica dentro da área visível', kb.saveBottom <= 430, JSON.stringify(kb));
  check('com o teclado, o campo em edição fica visível (não tapado)', kb.inputVisible, JSON.stringify(kb));
  await shot('06-teclado');
  await ev(`document.activeElement.blur(); __BCP.applyViewport({height:844,offsetTop:0})`); await sleep(200);
  check('ao fechar o teclado tudo volta ao normal', await ev(`!document.body.classList.contains('kb-open') && document.querySelector('#app').getBoundingClientRect().height===844`));

  // guardar
  await click('[data-act="save-week"]'); await until(() => ev('window.__saved!==null'), 4000);
  const saved = await ev('window.__saved');
  check('guarda as linhas certas (data, estações, comboios, horas, SIM)', saved && saved.newRows.length === 2 && saved.newRows.every(r => /^\d{4}-\d\d-\d\d$/.test(r[0]) && r[1] === 'Aveiro' && r[2] === 'Lisboa Oriente' && Number.isInteger(r[3]) && /^\d\d:\d\d$/.test(r[4]) && r[7] === 'SIM'), JSON.stringify(saved));
  const st = await ev(`window.__STATE.weekly.length`);
  check('não apaga as linhas de outras semanas (3 antigas + 2 novas)', st === 5, 'linhas=' + st);
  check('as linhas ficam ordenadas por data', await ev(`(()=>{const d=window.__STATE.weekly.map(r=>r[0]); return d.join()===[...d].sort().join()})()`));
  await until(() => ev(`document.querySelector('#editor').hidden`), 3000);
  await sleep(400);
  check('depois de guardar, o ecrã inicial mostra a semana como configurada', /configurada/.test(await text('#view')) && !/Falta configurar/.test(await text('#view')));
  await shot('07-semana-configurada');

  console.log('\n== Telemóvel estreito (360 px)');
  await send('Emulation.setDeviceMetricsOverride', { width: 360, height: 740, deviceScaleFactor: 2, mobile: true });
  await sleep(300);
  const overflow = () => ev(`(()=>{const w=innerWidth, bad=[...document.querySelectorAll('#view *, #editor *')].filter(e=>{const r=e.getBoundingClientRect(); return r.width>0 && (r.right>w+1||r.left<-1) && getComputedStyle(e).position!=='fixed'}); return bad.slice(0,3).map(e=>e.tagName+'.'+e.className+' '+Math.round(e.getBoundingClientRect().right))})()`);
  check('360px: nada sai do ecrã na página inicial', (await overflow()).length === 0, JSON.stringify(await overflow()));
  const rowRoute = await ev(`(()=>{const r=document.querySelector('.row .r'); return r? Math.round(r.getBoundingClientRect().height) : 0})()`);
  check('360px: o percurso da lista de compras cabe numa linha', rowRoute > 0 && rowRoute < 30, 'altura=' + rowRoute);
  await shot('09-semana-360');
  await click('[data-act="edit-week"]');
  await sleep(300);
  check('360px: nada sai do ecrã no editor', (await overflow()).length === 0, JSON.stringify(await overflow()));
  const selW = await ev(`(()=>{const s=document.querySelector('#editor [data-f="dest"]'); const c=document.createElement('canvas').getContext('2d'); const cs=getComputedStyle(s); c.font=cs.fontSize+' '+cs.fontFamily; const txt=s.options[s.selectedIndex].text; return {need:Math.ceil(c.measureText(txt).width)+parseFloat(cs.paddingLeft)+parseFloat(cs.paddingRight), have:Math.round(s.getBoundingClientRect().width), txt}})()`);
  check('360px: o destino "Lisboa Oriente" não fica cortado', selW.have >= selW.need, JSON.stringify(selW));
  await shot('10-editor-360');
  await click('[data-act="close-editor"]');
  await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });

  console.log('\n== Passe a expirar (estado de aviso)');
  await ev(`(async()=>{const t=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Lisbon'}).format(new Date()); const U=iso=>{const [y,m,d]=iso.split('-').map(Number);return Date.UTC(y,m-1,d)}; window.__STATE.passe[2]=Math.round((U(t)+2*864e5-Date.UTC(1899,11,30))/864e5); document.querySelector('#btnRefresh').click();})()`);
  await sleep(600);
  check('a 2 dias de expirar, o cartão do passe muda para aviso', await ev(`!!document.querySelector('.meter.warn')`) && /renova na App CP/.test(await text('#view')));

  console.log('\n== Manifest e service worker');
  const man = await ev(`fetch('manifest.webmanifest').then(r=>r.json())`);
  check('manifest tem nome, start_url, display, cores e ícones', man.name && man.start_url && man.display === 'standalone' && man.theme_color === '#008542' && man.icons.length >= 3);
  const iconOk = await ev(`Promise.all(${JSON.stringify(man.icons.map(i => i.src))}.map(s=>fetch(s).then(r=>r.ok&&r.headers.get('content-type').includes('image/png'))))`);
  check('todos os ícones do manifest existem (PNG)', iconOk.every(Boolean), JSON.stringify(iconOk));
  check('há um ícone maskable e ícones 192/512', man.icons.some(i => i.purpose === 'maskable') && man.icons.some(i => i.sizes === '192x192') && man.icons.some(i => i.sizes === '512x512'));
  check('apple-touch-icon e favicon existem', await ev(`Promise.all(['assets/apple-touch-icon.png','assets/favicon.ico','assets/favicon.png'].map(s=>fetch(s).then(r=>r.ok))).then(a=>a.every(Boolean))`));
  check('viewport, theme-color e manifest declarados', await ev(`!!document.querySelector('meta[name=viewport]')&&document.querySelector('meta[name=theme-color]').content==='#008542'&&!!document.querySelector('link[rel=manifest]')`));
  const swOk = await until(() => ev(`navigator.serviceWorker.getRegistration().then(r=>!!(r&&r.active))`), 25000);
  check('o service worker regista-se e fica ativo', !!swOk);
  if (swOk) {
    const caches = await ev(`caches.keys()`);
    check('o app shell foi guardado em cache (Workbox precache)', caches.some(k => /bilhetes-cp-precache/.test(k)), JSON.stringify(caches));
    await load();   // agora a página é controlada pelo SW
    await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0 });
    await load();
    check('OFFLINE: a app abre a partir da cache', (await ev('document.title')) === 'Bilhetes CP' && (await ev(`document.querySelector('#view').innerText.length>40`)));
    await shot('08-offline');
    await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
  } else problems.push('service worker não ficou ativo (Workbox vem de storage.googleapis.com: precisa de rede)');

  console.log('\n== Segurança');
  const html = await (await fetch(`http://127.0.0.1:${HTTP}/index.html`)).text() + await (await fetch(`http://127.0.0.1:${HTTP}/sw.js`)).text();
  check('nenhuma chave/segredo da CP no código da PWA', !/x-api-key['"]?\s*:\s*['"][0-9a-f]{16,}|connect-secret['"]?\s*:\s*['"][0-9a-f]{8,}/i.test(html) && !/(CP_API_KEY|CP_CONNECT_SECRET)\s*=\s*\S{8,}/.test(html));
  check('tudo o que vem da Sheet passa por esc() (sem innerHTML cru de dados)', !/innerHTML\s*=\s*[^;]*\$\{(?!esc\()[^}]*\b(r|t|l|d|h)\.(origin|dest|ref|err|result|tipo|hora)\b/.test(html));
} catch (e) {
  console.error('ERRO NO TESTE:', e.message); results.push({ name: 'execução do teste', ok: false });
}

console.log('\n== Problemas detetados no browser:', problems.length ? '' : 'nenhum'); problems.forEach(p => console.log('  - ' + p));
const bad = results.filter(r => !r.ok).length;
console.log(`\n${results.length - bad}/${results.length} verificações ok${bad ? `, ${bad} falharam` : ''}. Screenshots em ${SHOTS}`);
cleanup(); process.exit(bad || problems.some(p => p.startsWith('exceção')) ? 1 : 0);
