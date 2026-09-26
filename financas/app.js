/* Finanças — PWA. Dados na API do Raspberry Pi (tabelas financas_*), login Google. */
'use strict';

const APP_VERSION = 'v1.2.0';
const CLIENT_ID = '108256538530-fgunbb52s7f3s9aurfpjtaf01v8fjbph.apps.googleusercontent.com';
const API_URL = 'https://bmdpereira.duckdns.org/dados-api';
const SCOPES = 'openid email';
const CHART_URL = 'https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.5.0/chart.umd.min.js';
const CHART_SRI = 'sha384-XcdcwHqIPULERb2yDEM4R0XaQKU3YnDsrTmjACBZyfdVVqjh6xQ4/DCMd7XLcA6Y';
const TOKEN_KEY = 'financas_token', TOKEN_EXP_KEY = 'financas_token_exp';
const FILA_KEY = 'financas_fila', CACHE_KEY = 'financas_cache';

/* ---------- Ícones (SVG inline, nunca emojis) ---------- */
const P = {
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  wallet: '<path d="M20 12V8a2 2 0 0 0-2-2H5a2 2 0 0 1 0-4h13"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/><path d="M18 12a2 2 0 0 0 0 4h4v-4Z"/>',
  chart: '<path d="M3 3v18h18"/><path d="M7 16v-4M12 16V8M17 16v-6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  left: '<path d="m15 18-6-6 6-6"/>',
  right: '<path d="m9 18 6-6-6-6"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.4L21 8"/><path d="M21 3v5h-5"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>',
  repeat: '<path d="m17 2 4 4-4 4"/><path d="M3 11v-1a4 4 0 0 1 4-4h14M7 22l-4-4 4-4"/><path d="M21 13v1a4 4 0 0 1-4 4H3"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
};
const ico = (n) => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true">${P[n]}</svg>`;

/* ---------- Estado ---------- */
const S = {
  token: null, tokenClient: null, renovando: false,
  tab: 'lanc', mes: null, cats: [], lancs: [], atrasados: [],
  modo: localStorage.getItem('financas_modo') === '30d' ? '30d' : 'mes',
  resumo: null, rel: 'mensal', hist: null, histAno: null,
  edit: null, tipo: 'despesa', charts: {},
  base: { lancs: [], atrasados: [] },   // o que veio do servidor (ou da cache); S.lancs/S.atrasados = base + fila
  resumoBase: null, fila: [], offline: false, sincronizando: false,
  lembretes: null, editL: null, rep: 'unica',
};

/* ---------- Utilitários ---------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const pad = (n) => String(n).padStart(2, '0');
const EUR = new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' });
const eur = (v) => EUR.format(v || 0);
const isoDate = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const hoje = () => isoDate(new Date());
const mesDe = (iso) => iso.slice(0, 7);
const MESES = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
const MESES_C = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
const mesLabel = (m) => `${MESES[+m.slice(5) - 1]} ${m.slice(0, 4)}`;
const addMes = (m, n) => { const i = +m.slice(0, 4) * 12 + (+m.slice(5) - 1) + n; return `${Math.floor(i / 12)}-${pad((i % 12) + 1)}`; };
const ultimoDia = (m) => `${m}-${pad(new Date(+m.slice(0, 4), +m.slice(5), 0).getDate())}`;
const addDias = (iso, n) => { const d = new Date(iso + 'T00:00:00'); d.setDate(d.getDate() + n); return isoDate(d); };
const dataCurta = (iso) => `${+iso.slice(8)} ${MESES_C[+iso.slice(5, 7) - 1]}`;
const soma = (arr, f = (x) => x.valor) => arr.reduce((a, x) => a + f(x), 0);
const novoCid = () => (crypto.randomUUID ? crypto.randomUUID() : 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 12));
const corDe = (id) => (S.cats.find((c) => c.id === id) || {}).cor || '#8A918E';
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function estado(l) {
  if (l.data_pagamento) return 'pago';
  const h = hoje();
  return l.data_vencimento < h ? 'vencido' : l.data_vencimento === h ? 'hoje' : 'pendente';
}

/* ---------- Toast ---------- */
let toastTimer;
function toast(msg, acao) {
  const t = $('#toast');
  t.innerHTML = `<span>${esc(msg)}</span>`;
  if (acao) { const b = document.createElement('button'); b.type = 'button'; b.textContent = acao.texto; b.onclick = () => { t.classList.add('hidden'); acao.fn(); }; t.append(b); }
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), acao ? 6000 : 3200);
}
function mostrarErro(msg) { const e = $('#erro'); e.textContent = msg || ''; e.classList.toggle('hidden', !msg); }

/* ---------- Autenticação Google (mesmo padrão das outras apps) ---------- */
function guardarToken(t, seg) {
  try { localStorage.setItem(TOKEN_KEY, t); localStorage.setItem(TOKEN_EXP_KEY, String(Date.now() + (seg || 3600) * 1000 - 120000)); } catch (e) { /* sem storage */ }
}
function lerToken() {
  try {
    const t = localStorage.getItem(TOKEN_KEY), exp = +localStorage.getItem(TOKEN_EXP_KEY) || 0;
    return t && exp > Date.now() ? t : null;
  } catch (e) { return null; }
}
function limparToken() { try { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(TOKEN_EXP_KEY); } catch (e) { /* */ } }

function renovarSilencioso() {
  return new Promise((resolve) => {
    if (!S.tokenClient || S.renovando) return resolve(false);
    S.renovando = true;
    S.aoRenovar = (ok) => { S.renovando = false; resolve(ok); };
    try { S.tokenClient.requestAccessToken({ prompt: '' }); } catch (e) { S.aoRenovar(false); }
    setTimeout(() => { if (S.renovando) S.aoRenovar(false); }, 8000);
  });
}
function agendarRenovacao() {
  clearTimeout(S.tRenovar);
  let exp = 0; try { exp = +localStorage.getItem(TOKEN_EXP_KEY) || 0; } catch (e) { /* */ }
  const espera = Math.max(30000, exp - Date.now() - 180000);
  S.tRenovar = setTimeout(renovarSilencioso, espera);
}

function iniciarGoogle() {
  if (!window.google || !google.accounts) { $('#loginStatus').textContent = 'Falha ao carregar o início de sessão do Google. Recarrega a página.'; return; }
  S.tokenClient = google.accounts.oauth2.initTokenClient({
    client_id: CLIENT_ID, scope: SCOPES,
    error_callback: () => { if (S.aoRenovar) S.aoRenovar(false); },
    callback: (resp) => {
      if (S.renovando) {
        if (!resp.error) { S.token = resp.access_token; guardarToken(S.token, resp.expires_in); agendarRenovacao(); }
        S.aoRenovar(!resp.error); return;
      }
      if (resp.error) { if (resp.error !== 'interaction_required') $('#loginStatus').textContent = 'Falha no login: ' + resp.error; return; }
      S.token = resp.access_token; guardarToken(S.token, resp.expires_in); agendarRenovacao(); entrar();
    },
  });
}

/* ---------- API ---------- */
class ApiErro extends Error { constructor(m, status) { super(m); this.status = status; } }
const MSGS = { 403: 'Esta conta não tem acesso à app.', 409: 'Não é possível: o item está em uso ou já existe.', 429: 'Muitos pedidos. Espera um momento.', 503: 'Servidor ocupado. Tenta de novo.' };

async function api(metodo, caminho, corpo, repetir = true) {
  if (!navigator.onLine) throw new ApiErro('Sem ligação à internet', 0);
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 15000);
  let res;
  try {
    res = await fetch(API_URL + caminho, {
      method: metodo, signal: ctl.signal,
      headers: { Authorization: 'Bearer ' + S.token, ...(corpo !== undefined ? { 'Content-Type': 'application/json' } : {}) },
      body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
    });
  } catch (e) { throw new ApiErro('Não foi possível contactar o servidor', 0); } finally { clearTimeout(timer); }
  if (res.status === 401) {
    if (repetir && await renovarSilencioso()) return api(metodo, caminho, corpo, false);
    sessaoExpirada(); throw new ApiErro('Sessão expirada', 401);
  }
  let dados = null; try { dados = await res.json(); } catch (e) { /* sem corpo */ }
  if (!res.ok) throw new ApiErro(MSGS[res.status] || (dados && dados.erro && dados.erro.mensagem) || `Erro do servidor (${res.status})`, res.status);
  return dados;
}
function sessaoExpirada() { S.token = null; limparToken(); $('#app').classList.add('hidden'); $('#login').classList.remove('hidden'); $('#loginStatus').textContent = 'Sessão expirada. Entra outra vez.'; }

/* ---------- Fila offline e cache de leitura ----------
   Toda a escrita passa pela fila (localStorage): a lista mostra logo o resultado e a fila sincroniza quando há rede.
   criar é idempotente pelo `cid`; editar/apagar repetidos dão o mesmo resultado (apagar um 404 conta como feito).
   Um lançamento criado offline tem o id temporário 'c:<cid>'; editá-lo/apagá-lo antes de sincronizar mexe no próprio pedido. */
function lerJson(k, def) { try { const v = JSON.parse(localStorage.getItem(k)); return v ?? def; } catch (e) { return def; } }
function gravarJson(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* sem storage */ } }
function gravarFila() { if (S.fila.length) gravarJson(FILA_KEY, S.fila); else { try { localStorage.removeItem(FILA_KEY); } catch (e) { /* */ } } }
const ehTemp = (id) => typeof id === 'string';
const idDe = (v) => (/^\d+$/.test(v) ? +v : v);
const nomeCat = (id) => (S.cats.find((c) => c.id === id) || {}).nome || '';
const porVenc = (a, b) => (a.data_vencimento < b.data_vencimento ? -1 : a.data_vencimento > b.data_vencimento ? 1 : 0);

function enfileirar(op) {
  const f = S.fila;
  if (op.op === 'criar') f.push(op);
  else if (op.op === 'editar') {
    if (ehTemp(op.id)) { const c = f.find((x) => x.op === 'criar' && 'c:' + x.cid === op.id); if (c) Object.assign(c.corpo, op.corpo); }
    else { const e = f.find((x) => x.op === 'editar' && x.id === op.id); if (e) Object.assign(e.corpo, op.corpo); else f.push(op); }
  } else if (op.op === 'apagar') {
    if (ehTemp(op.id)) S.fila = f.filter((x) => !(x.op === 'criar' && 'c:' + x.cid === op.id));
    else { S.fila = f.filter((x) => !(x.op === 'editar' && x.id === op.id)); if (!S.fila.some((x) => x.op === 'apagar' && x.id === op.id)) S.fila.push(op); }
  }
  gravarFila();
}

function aplicarOps(mapa) {
  for (const o of S.fila) {
    if (o.op === 'criar') {
      const c = o.corpo, id = 'c:' + o.cid;
      mapa.set(id, { id, tipo: c.tipo, descricao: c.descricao, valor: c.valor, categoria_id: c.categoria_id, categoria: nomeCat(c.categoria_id),
        data_vencimento: c.data_vencimento, data_pagamento: c.data_pagamento ?? null, recorrente: !!c.recorrente, mes_referencia: c.mes_referencia || c.data_vencimento.slice(0, 7) });
    } else if (o.op === 'editar') {
      const it = mapa.get(o.id);
      if (it) { Object.assign(it, o.corpo); if (o.corpo.categoria_id !== undefined) it.categoria = nomeCat(it.categoria_id); }
    } else mapa.delete(o.id);
  }
  return mapa;
}

/* Recalcula o que a interface mostra: dados do servidor + alterações ainda na fila. */
function recomputar() {
  const h = hoje(), m = new Map();
  for (const x of S.base.lancs.concat(S.base.atrasados)) if (!m.has(x.id)) m.set(x.id, { ...x });
  const todos = [...aplicarOps(m).values()];
  S.lancs = todos.filter((x) => x.mes_referencia === S.mes).sort(porVenc);
  S.atrasados = todos.filter((x) => x.tipo === 'despesa' && !x.data_pagamento && x.data_vencimento < h).sort(porVenc);
  if (S.resumoBase && S.janela) {
    const r = new Map(S.resumoBase.map((x) => [x.id, { ...x }]));
    S.resumo = [...aplicarOps(r).values()].filter((x) => x.data_vencimento >= S.janela.de && x.data_vencimento <= S.janela.ate).sort(porVenc);
  }
}

async function sincronizar() {
  if (S.sincronizando || !S.fila.length || !S.token) return false;
  S.sincronizando = true; let mudou = false;
  try {
    while (S.fila.length) {
      const o = S.fila[0];
      try {
        if (o.op === 'criar') await api('POST', '/financas/lancamentos', { ...o.corpo, cid: o.cid });
        else if (o.op === 'editar') await api('PUT', `/financas/lancamentos/${o.id}`, o.corpo);
        else await api('DELETE', `/financas/lancamentos/${o.id}`);
      } catch (e) {
        if (e.status === 0 || e.status === 401 || e.status === 429 || e.status >= 500) break;   // fica na fila, tenta mais tarde
        if (e.status !== 404) toast('Uma alteração foi recusada pelo servidor: ' + e.message);  // 4xx: descarta para não bloquear a fila
      }
      S.fila.shift(); mudou = true; gravarFila();
    }
  } finally { S.sincronizando = false; }
  return mudou;
}

function guardarCache() {
  const c = lerJson(CACHE_KEY, { meses: {} });
  c.cats = S.cats; c.meses = c.meses || {}; c.meses[S.mes] = { lancs: S.base.lancs, atrasados: S.base.atrasados };
  const ks = Object.keys(c.meses).sort();
  while (ks.length > 8) delete c.meses[ks.shift()];
  gravarJson(CACHE_KEY, c);
}

function renderSync() {
  const n = S.fila.length, off = !navigator.onLine || S.offline;
  $('#bannerSync').innerHTML = n || off
    ? `<div class="banner info" role="status">${ico('info')}<div class="grow">${off ? 'Sem ligação. ' : ''}${n ? `<b>${n}</b> ${n === 1 ? 'alteração por sincronizar' : 'alterações por sincronizar'}.` : 'A mostrar os últimos dados guardados.'}</div></div>` : '';
}

/* Aplica já o que o utilizador fez e sincroniza em segundo plano. */
async function aplicarAcao() {
  invalidarHistorico(); recomputar(); renderTudo();
  if (await sincronizar()) await carregarMes({ silencioso: true });
  else renderSync();
}

/* ---------- Carregamento ---------- */
const qs = (o) => '?' + new URLSearchParams(o).toString();

async function carregarMes({ silencioso = false } = {}) {
  mostrarErro('');
  if (S.fila.length) await sincronizar();
  if (!silencioso) $('#listaLanc').innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>';
  try {
    if (!S.cats.length) S.cats = (await api('GET', '/financas/categorias')).categorias;
    // Ao abrir um mês (até ao seguinte) vem por omissão o mês anterior; o servidor só o faz uma vez por mês.
    S.preparado = null;
    if (S.mes <= addMes(mesDe(hoje()), 1)) {
      const p = await api('POST', `/financas/meses/${S.mes}/preparar`, {});
      if (p.criados > 0) S.preparado = { origem: p.origem, n: p.criados };
    }
    const [l, a] = await Promise.all([
      api('GET', '/financas/lancamentos' + qs({ mes: S.mes })),
      api('GET', '/financas/lancamentos' + qs({ pendentes: 1, ate: addDias(hoje(), -1) })),
    ]);
    S.base = { lancs: l.lancamentos, atrasados: a.lancamentos.filter((x) => x.tipo === 'despesa') };
    S.offline = false; guardarCache();
  } catch (e) {
    if (e.status === 0) {   // sem rede: mostra o último estado guardado
      S.offline = true;
      const c = lerJson(CACHE_KEY, null);
      if (c) { if (!S.cats.length) S.cats = c.cats || []; const m = c.meses && c.meses[S.mes]; S.base = m ? { lancs: m.lancs, atrasados: m.atrasados } : { lancs: [], atrasados: S.base.atrasados }; }
      else mostrarErro(e.message);
    } else if (e.status !== 401) mostrarErro(e.message);
  }
  recomputar(); renderTudo();
}

async function carregarResumo() {
  const h = hoje();
  const [de, ate] = S.modo === 'mes' ? [S.mes + '-01', ultimoDia(S.mes)] : [h, addDias(h, 29)];
  S.janela = { de, ate };
  try {
    S.resumoBase = (await api('GET', '/financas/lancamentos' + qs({ de, ate }))).lancamentos;
    mostrarErro('');
  } catch (e) {
    if (e.status === 0 && !S.resumoBase) {   // offline: monta a janela com os meses em cache
      const c = lerJson(CACHE_KEY, null), vistos = new Map();
      Object.values((c && c.meses) || {}).forEach((m) => m.lancs.forEach((x) => vistos.set(x.id, x)));
      S.resumoBase = [...vistos.values()];
    } else if (e.status !== 401 && e.status !== 0) mostrarErro(e.message);
    S.resumoBase = S.resumoBase || [];
  }
  recomputar(); renderResumo();
}

async function carregarHistorico() {
  const ano = +S.mes.slice(0, 4);
  if (S.hist && S.histAno === ano) return S.hist;
  try {
    S.hist = (await api('GET', '/financas/agregado' + qs({ de: `${ano - 2}-01`, ate: `${ano}-12` }))).linhas;
    S.histAno = ano;
  } catch (e) { if (e.status !== 401) mostrarErro(e.message); S.hist = S.hist || []; }
  return S.hist;
}
const invalidarHistorico = () => { S.hist = null; };

/* ---------- Render: lançamentos ---------- */
function linhaLanc(l) {
  const st = estado(l);
  const sub = st === 'pago' ? `Pago a ${dataCurta(l.data_pagamento)}`
    : st === 'vencido' ? `<span class="late">Venceu a ${dataCurta(l.data_vencimento)}</span>`
    : st === 'hoje' ? `<span class="today">Vence hoje</span>` : `Vence a ${dataCurta(l.data_vencimento)}`;
  const pend = ehTemp(l.id) ? ' · por sincronizar' : '';
  const sinal = l.tipo === 'rendimento' ? '+' : '';
  return `<div class="row ${st === 'pago' ? 'paid' : ''}" data-id="${esc(l.id)}" role="button" tabindex="0">
    <button class="check ${st === 'pago' ? 'on' : ''}" type="button" data-pagar="${esc(l.id)}" aria-label="${st === 'pago' ? 'Desmarcar como pago' : 'Marcar como pago'}">${ico('check')}</button>
    <span class="dot" style="background:${esc(corDe(l.categoria_id))}"></span>
    <div class="main"><div class="desc">${esc(l.descricao)}${l.recorrente ? ico('repeat') : ''}</div><div class="sub">${esc(l.categoria)} · ${sub}${pend}</div></div>
    <div class="amt ${l.tipo === 'rendimento' ? 'pos' : ''}">${sinal}${eur(l.valor)}</div></div>`;
}

function renderLancamentos() {
  const L = S.lancs, dep = L.filter((x) => x.tipo === 'despesa'), ren = L.filter((x) => x.tipo === 'rendimento');
  const porPagar = soma(dep.filter((x) => !x.data_pagamento));
  $('#totaisMes').innerHTML = `
    <div class="total"><div class="k">Rendimento</div><div class="v pos">${eur(soma(ren))}</div></div>
    <div class="total"><div class="k">Despesas</div><div class="v">${eur(soma(dep))}</div></div>
    <div class="total"><div class="k">Por pagar</div><div class="v ${porPagar > 0 ? 'neg' : ''}">${eur(porPagar)}</div></div>`;

  // Avisos ligados a uma condição que se mantém: ficam visíveis enquanto a condição durar (não são toasts).
  const at = S.atrasados;
  $('#bannerAtraso').innerHTML = at.length
    ? `<div class="banner warn" role="status">${ico('alert')}<div class="grow"><b>${at.length} ${at.length === 1 ? 'despesa vencida e por pagar' : 'despesas vencidas e por pagar'}</b> · ${eur(soma(at))}<br><button class="link" type="button" data-ir="resumo">Ver quais</button></div></div>` : '';
  const dispensado = (() => { try { return localStorage.getItem('financas_prep_' + S.mes) === '1'; } catch (e) { return false; } })();
  $('#bannerPreparado').innerHTML = S.preparado && !dispensado
    ? `<div class="banner info">${ico('info')}<div class="grow">Lista preparada a partir de <b>${esc(mesLabel(S.preparado.origem))}</b> (${S.preparado.n} lançamentos). Revê os valores que mudaram, remove o que não se aplica e acrescenta o que falta.</div><button class="x" type="button" data-fechar-prep aria-label="Fechar">${ico('x')}</button></div>` : '';

  if (!L.length) {
    $('#listaLanc').innerHTML = `<div class="empty">${ico('wallet')}<p>Sem lançamentos em ${esc(mesLabel(S.mes))}.<br>Toca em + para adicionar o primeiro.</p></div>`;
    return;
  }
  const grupos = [['Por pagar / receber', L.filter((x) => !x.data_pagamento)], ['Pagos / recebidos', L.filter((x) => x.data_pagamento)]];
  $('#listaLanc').innerHTML = grupos.filter(([, g]) => g.length).map(([t, g]) =>
    `<div class="group-title"><span>${t}</span><span>${g.length}</span></div><div class="list">${g.map(linhaLanc).join('')}</div>`).join('');
}

/* ---------- Render: resumo (ativo / passivo) ---------- */
function renderResumo() {
  if (!S.resumo) { $('#resumoCorpo').innerHTML = '<div class="skeleton"></div>'; return; }
  const { de, ate } = S.janela;
  $('#janelaTxt').textContent = `${dataCurta(de)} – ${dataCurta(ate)}`;
  $$('[data-modo]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === S.modo)));
  const R = S.resumo, ren = R.filter((x) => x.tipo === 'rendimento'), dep = R.filter((x) => x.tipo === 'despesa');
  const rendimento = soma(ren), pend = soma(dep.filter((x) => !x.data_pagamento)), saldo = rendimento - pend;
  const antes = S.atrasados.filter((x) => x.data_vencimento < de);   // vencidas antes desta janela
  const emAtraso = soma(antes);
  let html = `<div class="card"><h2>Ativo − passivo</h2>
    <div class="kv"><span>Rendimento</span><span class="pos">${eur(rendimento)}</span></div>
    <div class="kv"><span>Despesas por pagar</span><span>− ${eur(pend)}</span></div>
    <div class="kv total-line"><span>Saldo do período</span><span class="${saldo >= 0 ? 'pos' : 'neg'}">${eur(saldo)}</span></div>
    ${saldo < 0 ? `<p class="muted" style="margin:8px 0 0">Défice de ${eur(-saldo)}: será preciso cobrir com liquidez ou crédito.</p>` : ''}
    ${emAtraso > 0 ? `<p class="muted" style="margin:8px 0 0">Com as vencidas de antes do período (${eur(emAtraso)}): <b class="${saldo - emAtraso >= 0 ? 'pos' : 'neg'}">${eur(saldo - emAtraso)}</b></p>` : ''}</div>`;

  if (S.atrasados.length) {
    html += `<div class="card"><h2>Vencidos e não pagos</h2><div class="list" style="box-shadow:none;border:0">${S.atrasados.map(linhaLanc).join('')}</div></div>`;
  }
  const porCat = agruparPorCategoria(dep);
  html += `<div class="card"><h2>Despesas por categoria</h2>${porCat.length ? `<div class="chart-wrap short"><canvas id="cvResumo" role="img" aria-label="Despesas por categoria"></canvas></div>${legenda(porCat)}` : '<p class="muted">Sem despesas neste período.</p>'}</div>`;
  $('#resumoCorpo').innerHTML = html;
  if (porCat.length) desenhar('resumo', 'cvResumo', { type: 'doughnut', data: { labels: porCat.map((c) => c.nome), datasets: [{ data: porCat.map((c) => c.total), backgroundColor: porCat.map((c) => c.cor), borderColor: css('--card'), borderWidth: 2 }] }, options: { maintainAspectRatio: false, cutout: '62%', plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ` ${c.label}: ${eur(c.parsed)}` } } } } });
}

function agruparPorCategoria(arr) {
  const m = new Map();
  arr.forEach((l) => { const c = m.get(l.categoria_id) || { nome: l.categoria, cor: corDe(l.categoria_id), total: 0 }; c.total += l.valor; m.set(l.categoria_id, c); });
  return [...m.values()].sort((a, b) => b.total - a.total);
}
const legenda = (cats) => `<div class="legend">${cats.map((c) => `<span><i style="background:${esc(c.cor)}"></i>${esc(c.nome)} ${eur(c.total)}</span>`).join('')}</div>`;

/* ---------- Gráficos (Chart.js carregado só quando preciso) ---------- */
let chartPromise;
function carregarChart() {
  if (window.Chart) return Promise.resolve();
  if (!chartPromise) chartPromise = new Promise((ok, ko) => {
    const s = document.createElement('script'); s.src = CHART_URL; s.integrity = CHART_SRI; s.crossOrigin = 'anonymous';
    s.onload = ok; s.onerror = () => { chartPromise = null; ko(new Error('Não foi possível carregar os gráficos (sem ligação?)')); };
    document.head.append(s);
  });
  return chartPromise;
}
async function desenhar(chave, canvasId, cfg) {
  try { await carregarChart(); } catch (e) { mostrarErro(e.message); return; }
  const cv = document.getElementById(canvasId);
  if (!cv) return;
  if (S.charts[chave]) S.charts[chave].destroy();
  Chart.defaults.color = css('--muted'); Chart.defaults.font.family = css('--font') || 'sans-serif';
  Chart.defaults.borderColor = css('--border');
  S.charts[chave] = new Chart(cv, cfg);
}

/* ---------- Render: relatórios ---------- */
async function renderRelatorio() {
  $$('[data-rel]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.rel === S.rel)));
  const el = $('#relCorpo');
  if (S.rel === 'mensal') return relMensal(el);
  el.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  const linhas = await carregarHistorico();
  if (S.tab !== 'rel') return;
  if (S.rel === 'anual') relAnual(el, linhas);
  else if (S.rel === 'homologo') relHomologo(el, linhas);
  else relConta(el, linhas);
}

function relMensal(el) {
  const dep = S.lancs.filter((x) => x.tipo === 'despesa'), ren = S.lancs.filter((x) => x.tipo === 'rendimento');
  const td = soma(dep), tr = soma(ren), cats = agruparPorCategoria(dep), max = cats.length ? cats[0].total : 1;
  el.innerHTML = `<div class="card"><h2>${esc(mesLabel(S.mes))}</h2>
    <div class="totals" style="margin:0 0 6px"><div class="total"><div class="k">Rendimento</div><div class="v pos">${eur(tr)}</div></div>
    <div class="total"><div class="k">Despesas</div><div class="v">${eur(td)}</div></div>
    <div class="total"><div class="k">Resultado</div><div class="v ${tr - td >= 0 ? 'pos' : 'neg'}">${eur(tr - td)}</div></div></div></div>
    <div class="card"><h2>Despesas por categoria</h2>${cats.length ? cats.map((c) => `<div class="bar-line"><span class="name">${esc(c.nome)}</span><span class="track"><span class="fill" style="display:block;width:${(c.total / max * 100).toFixed(1)}%;background:${esc(c.cor)}"></span></span><span class="val">${eur(c.total)}</span></div>`).join('') : '<p class="muted">Sem despesas neste mês.</p>'}</div>`;
}

function relAnual(el, linhas) {
  const ano = +S.mes.slice(0, 4), meses = Array.from({ length: 12 }, (_, i) => `${ano}-${pad(i + 1)}`);
  const doAno = linhas.filter((l) => l.mes.startsWith(String(ano)));
  const cats = S.cats.filter((c) => doAno.some((l) => l.tipo === 'despesa' && l.categoria_id === c.id));
  const ds = cats.map((c) => ({ type: 'bar', label: c.nome, backgroundColor: c.cor, stack: 'd', data: meses.map((m) => soma(doAno.filter((l) => l.mes === m && l.tipo === 'despesa' && l.categoria_id === c.id), (x) => x.total)) }));
  const rend = meses.map((m) => soma(doAno.filter((l) => l.mes === m && l.tipo === 'rendimento'), (x) => x.total));
  ds.push({ type: 'line', label: 'Rendimento', borderColor: css('--income'), backgroundColor: css('--income'), tension: .25, pointRadius: 3, data: rend });
  const totD = soma(doAno.filter((l) => l.tipo === 'despesa'), (x) => x.total), totR = soma(rend, (x) => x);
  el.innerHTML = `<div class="card"><h2>Evolução em ${ano}</h2>
    <div class="chart-wrap"><canvas id="cvAnual" role="img" aria-label="Despesas e rendimento mês a mês"></canvas></div>
    <p class="muted" style="margin:10px 0 0">Total do ano: rendimento <b class="pos">${eur(totR)}</b> · despesas <b>${eur(totD)}</b> · resultado <b class="${totR - totD >= 0 ? 'pos' : 'neg'}">${eur(totR - totD)}</b></p></div>
    <p class="muted">Muda o ano com as setas do mês.</p>`;
  desenhar('anual', 'cvAnual', { data: { labels: meses.map((m) => MESES_C[+m.slice(5) - 1]), datasets: ds }, options: { maintainAspectRatio: false, scales: { x: { stacked: true }, y: { stacked: true, ticks: { callback: (v) => v + ' €' } } }, plugins: { legend: { position: 'bottom', labels: { boxWidth: 10 } }, tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${eur(c.parsed.y)}` } } } } });
}

function assuntos(linhas) {
  const l = [{ k: 'td', nome: 'Total de despesas', f: (x) => x.tipo === 'despesa' }, { k: 'tr', nome: 'Total de rendimentos', f: (x) => x.tipo === 'rendimento' }];
  S.cats.forEach((c) => { if (linhas.some((x) => x.tipo === 'despesa' && x.categoria_id === c.id)) l.push({ k: 'c' + c.id, nome: 'Categoria: ' + c.nome, f: (x) => x.tipo === 'despesa' && x.categoria_id === c.id }); });
  [...new Set(linhas.map((x) => x.descricao.toLowerCase()))].sort().forEach((d) => l.push({ k: 'd' + d, nome: 'Conta: ' + d, f: (x) => x.descricao.toLowerCase() === d }));
  return l;
}
function seletorAssunto(lista, atual) { return `<label class="f" for="selAssunto">Ver</label><select id="selAssunto">${lista.map((a) => `<option value="${esc(a.k)}" ${a.k === atual ? 'selected' : ''}>${esc(a.nome)}</option>`).join('')}</select>`; }

function relHomologo(el, linhas) {
  const lista = assuntos(linhas), a = lista.find((x) => x.k === S.assunto) || lista.find((x) => x.k === 'td') || lista[0];
  S.assunto = a.k;
  const mm = S.mes.slice(5), ano = +S.mes.slice(0, 4), anos = [ano - 2, ano - 1, ano];
  const vals = anos.map((y) => soma(linhas.filter((l) => l.mes === `${y}-${mm}` && a.f(l)), (x) => x.total));
  const delta = (i) => (vals[i - 1] > 0 ? `${vals[i] >= vals[i - 1] ? '+' : ''}${((vals[i] - vals[i - 1]) / vals[i - 1] * 100).toFixed(1).replace('.', ',')} %` : '—');
  el.innerHTML = `<div class="card"><h2>${MESES[+mm - 1]}: ${anos[0]} · ${anos[1]} · ${anos[2]}</h2>${seletorAssunto(lista, a.k)}
    <div class="chart-wrap short" style="margin-top:14px"><canvas id="cvHom" role="img" aria-label="Comparação do mesmo mês em anos diferentes"></canvas></div>
    <table class="simple" style="margin-top:10px"><tr><th>Ano</th><th>Valor</th><th>vs. ano anterior</th></tr>${anos.map((y, i) => `<tr><td>${y}</td><td>${eur(vals[i])}</td><td>${i ? delta(i) : '—'}</td></tr>`).join('')}</table></div>`;
  $('#selAssunto').onchange = (e) => { S.assunto = e.target.value; relHomologo(el, linhas); };
  desenhar('hom', 'cvHom', { type: 'bar', data: { labels: anos.map(String), datasets: [{ data: vals, backgroundColor: [css('--info'), css('--secondary'), css('--primary')], borderRadius: 6 }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ' ' + eur(c.parsed.y) } } }, scales: { y: { beginAtZero: true, ticks: { callback: (v) => v + ' €' } } } } });
}

function relConta(el, linhas) {
  const lista = assuntos(linhas).filter((x) => x.k.startsWith('d') || x.k.startsWith('c')), a = lista.find((x) => x.k === S.conta) || lista[0];
  if (!a) { el.innerHTML = '<div class="empty">Ainda não há dados para o histórico.</div>'; return; }
  S.conta = a.k;
  const fim = S.mes, meses = Array.from({ length: 24 }, (_, i) => addMes(fim, i - 23));
  const vals = meses.map((m) => soma(linhas.filter((l) => l.mes === m && a.f(l)), (x) => x.total));
  el.innerHTML = `<div class="card"><h2>Últimos 24 meses até ${esc(mesLabel(fim))}</h2>${seletorAssunto(lista, a.k)}
    <div class="chart-wrap" style="margin-top:14px"><canvas id="cvConta" role="img" aria-label="Evolução mensal da conta escolhida"></canvas></div></div>`;
  $('#selAssunto').onchange = (e) => { S.conta = e.target.value; relConta(el, linhas); };
  desenhar('conta', 'cvConta', { type: 'line', data: { labels: meses.map((m) => `${MESES_C[+m.slice(5) - 1]} ${m.slice(2, 4)}`), datasets: [{ data: vals, borderColor: css('--primary'), backgroundColor: css('--primary'), tension: .25, pointRadius: 3, spanGaps: true }] }, options: { maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => ' ' + eur(c.parsed.y) } } }, scales: { y: { beginAtZero: true, ticks: { callback: (v) => v + ' €' } } } } });
}

/* ---------- Render: ajustes (categorias) ---------- */
function renderCategorias() {
  $('#listaCats').innerHTML = S.cats.map((c) => `<div class="cat-row" data-cat="${c.id}">
    <input type="color" value="${esc(c.cor.toLowerCase())}" aria-label="Cor de ${esc(c.nome)}" data-cor>
    <input type="text" value="${esc(c.nome)}" maxlength="40" aria-label="Nome da categoria" data-nome>
    <button class="icon-btn" type="button" data-apagar-cat aria-label="Apagar ${esc(c.nome)}">${ico('trash')}</button></div>`).join('');
}

/* ---------- Render geral ---------- */
function renderTudo() {
  $('#mesLabel').textContent = mesLabel(S.mes);
  renderLancamentos();
  renderSync();
  if (S.tab === 'resumo') { if (S.resumo) renderResumo(); else carregarResumo(); }
  if (S.tab === 'rel') renderRelatorio();
  if (S.tab === 'ajustes') renderCategorias();
}

function mostrarTab(t) {
  S.tab = t;
  $$('.tab').forEach((x) => x.classList.toggle('active', x.id === 'tab-' + t));
  $$('nav.tabs button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === t)));
  $('#monthNav').style.visibility = t === 'ajustes' || t === 'lemb' ? 'hidden' : 'visible';
  $('#fab').classList.toggle('hidden', t === 'ajustes');
  window.scrollTo(0, 0);
  if (t === 'resumo') carregarResumo();
  if (t === 'rel') renderRelatorio();
  if (t === 'lemb') { renderLembretes(); carregarLembretes(); }
  if (t === 'ajustes') renderCategorias();
}

/* ---------- Lembretes (avisos ntfy agendados; precisam de rede, não passam pela fila offline) ---------- */
async function carregarLembretes() {
  try { S.lembretes = (await api('GET', '/financas/lembretes')).lembretes; mostrarErro(''); }
  catch (e) { if (e.status !== 401) mostrarErro(e.status === 0 ? 'Os lembretes precisam de ligação à internet.' : e.message); S.lembretes = S.lembretes || []; }
  renderLembretes();
}

function proximoAviso(l) {
  const h = hoje();
  if (l.repeticao === 'unica') return l.data;
  const dia = (m) => `${m}-${pad(Math.min(+l.data.slice(8), +ultimoDia(m).slice(8)))}`;
  let m = mesDe(h < l.data ? l.data : h), c = dia(m);
  if (c < h || (c === h && l.ultimo_aviso === h)) { m = addMes(m, 1); c = dia(m); }
  return c;
}

function renderLembretes() {
  const el = $('#listaLemb');
  if (!S.lembretes) { el.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>'; return; }
  if (!S.lembretes.length) { el.innerHTML = `<div class="empty">${ico('bell')}<p>Ainda não tens lembretes.<br>Toca em + para agendar o primeiro.</p></div>`; return; }
  const h = hoje();
  el.innerHTML = `<div class="list">${S.lembretes.map((l) => {
    const unica = l.repeticao === 'unica', enviado = unica && l.ultimo_aviso;
    const quando = unica
      ? (enviado ? `Enviado a ${dataCurta(l.data)}` : l.data < h ? `Passou a ${dataCurta(l.data)}` : `${dataCurta(l.data)} às ${l.hora}`)
      : `Próximo: ${dataCurta(proximoAviso(l))} às ${l.hora}`;
    return `<div class="row ${l.ativo ? '' : 'off'}" data-lemb="${l.id}" role="button" tabindex="0">
      <span class="dot" style="background:var(--${l.ativo ? 'primary' : 'muted'})"></span>
      <div class="main"><div class="desc">${esc(l.titulo)}</div><div class="sub"><span class="badge">${unica ? 'Uma vez' : 'Todos os meses'}</span> ${esc(quando)}${l.nota ? ' · ' + esc(l.nota) : ''}</div></div>
      <input class="toggle" type="checkbox" data-lemb-ativo="${l.id}" ${l.ativo ? 'checked' : ''} aria-label="Ativo">
    </div>`;
  }).join('')}</div>`;
}

function pintarRep() {
  $$('[data-rep]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.rep === S.rep)));
  const d = $('#lData').value;
  $('#lAjuda').textContent = S.rep === 'mensal'
    ? `Repete-se todos os meses no dia ${d ? +d.slice(8) : '…'}${d && +d.slice(8) > 28 ? ' (nos meses mais curtos, no último dia)' : ''}, a partir desta data.`
    : 'Avisa uma só vez, no dia e hora escolhidos.';
}

function abrirSheetLemb(l) {
  S.editL = l || null; S.rep = l ? l.repeticao : 'unica';
  $('#sheetLTitulo').textContent = l ? 'Editar lembrete' : 'Novo lembrete';
  $('#lTit').value = l ? l.titulo : ''; $('#lNota').value = l ? l.nota : '';
  $('#lData').value = l ? l.data : hoje(); $('#lHora').value = l ? l.hora : '09:00';
  $('#lErro').textContent = ''; $('#lApagar').classList.toggle('hidden', !l);
  pintarRep();
  $('#scrim').classList.remove('hidden'); $('#sheetL').classList.remove('hidden');
  requestAnimationFrame(() => { $('#scrim').classList.add('on'); $('#sheetL').classList.add('on'); if (!l) $('#lTit').focus(); });
}

async function guardarLembrete(ev) {
  ev.preventDefault();
  const corpo = { titulo: $('#lTit').value.trim(), nota: $('#lNota').value.trim(), data: $('#lData').value, hora: $('#lHora').value, repeticao: S.rep };
  if (!corpo.titulo) return ($('#lErro').textContent = 'Indica um título.');
  if (!corpo.data) return ($('#lErro').textContent = 'Indica a data.');
  if (!corpo.hora) return ($('#lErro').textContent = 'Indica a hora.');
  $('#lGuardar').disabled = true;
  try {
    if (S.editL) await api('PUT', `/financas/lembretes/${S.editL.id}`, corpo); else await api('POST', '/financas/lembretes', corpo);
    fecharSheet(); toast('Lembrete guardado'); await carregarLembretes();
  } catch (e) { $('#lErro').textContent = e.message; } finally { $('#lGuardar').disabled = false; }
}

async function apagarLembrete() {
  const l = S.editL; if (!l) return;
  try {
    const apagado = await api('DELETE', `/financas/lembretes/${l.id}`);
    fecharSheet(); await carregarLembretes();
    toast('Lembrete apagado', { texto: 'Desfazer', fn: async () => {
      try { const { titulo, nota, data, hora, repeticao, ativo } = apagado; await api('POST', '/financas/lembretes', { titulo, nota, data, hora, repeticao, ativo }); await carregarLembretes(); }
      catch (e) { toast(e.message); }
    } });
  } catch (e) { $('#lErro').textContent = e.message; }
}

/* ---------- Ações sobre lançamentos (todas passam pela fila) ---------- */
async function alternarPago(id) {
  const l = S.lancs.find((x) => x.id === id) || S.atrasados.find((x) => x.id === id);
  if (!l) return;
  const novo = l.data_pagamento ? null : hoje();
  enfileirar({ op: 'editar', id, corpo: { data_pagamento: novo } });
  toast(novo ? 'Marcado como pago' : 'Pagamento desfeito');
  await aplicarAcao();
}

async function recarregarTudo() {
  await carregarMes({ silencioso: true });
}

function abrirSheet(l) {
  S.edit = l || null;
  S.tipo = l ? l.tipo : 'despesa';
  $('#sheetTitulo').textContent = l ? 'Editar lançamento' : 'Novo lançamento';
  $('#fCat').innerHTML = S.cats.map((c) => `<option value="${c.id}">${esc(c.nome)}</option>`).join('');
  $('#fDesc').value = l ? l.descricao : '';
  $('#fValor').value = l ? l.valor : '';
  $('#fCat').value = l ? l.categoria_id : (S.cats.find((c) => c.nome === 'Outros') || S.cats[0]).id;
  const dia = S.mes === mesDe(hoje()) ? hoje() : S.mes + '-01';
  $('#fVenc').value = l ? l.data_vencimento : dia;
  $('#fPag').value = l && l.data_pagamento ? l.data_pagamento : '';
  $('#fRec').checked = l ? l.recorrente : false;
  $('#fErro').textContent = '';
  $('#fApagar').classList.toggle('hidden', !l);
  pintarTipo();
  $('#scrim').classList.remove('hidden'); $('#sheet').classList.remove('hidden');
  requestAnimationFrame(() => { $('#scrim').classList.add('on'); $('#sheet').classList.add('on'); if (!l) $('#fDesc').focus(); });
}
function fecharSheet() {
  $('#scrim').classList.remove('on'); $$('.sheet').forEach((x) => x.classList.remove('on'));
  setTimeout(() => { $('#scrim').classList.add('hidden'); $$('.sheet').forEach((x) => x.classList.add('hidden')); }, 250);
}
function pintarTipo() {
  $$('[data-tipo]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tipo === S.tipo)));
  if (!S.edit && S.tipo === 'rendimento') { const r = S.cats.find((c) => c.nome === 'Rendimentos'); if (r) $('#fCat').value = r.id; }
}

async function guardarSheet(ev) {
  ev.preventDefault();
  const valor = parseFloat(String($('#fValor').value).replace(',', '.'));
  const corpo = {
    tipo: S.tipo, descricao: $('#fDesc').value.trim(), valor, categoria_id: +$('#fCat').value,
    data_vencimento: $('#fVenc').value, data_pagamento: $('#fPag').value || null, recorrente: $('#fRec').checked,
  };
  if (!corpo.descricao) return ($('#fErro').textContent = 'Indica uma descrição.');
  if (!(valor > 0)) return ($('#fErro').textContent = 'Indica um valor maior que zero.');
  if (!corpo.data_vencimento) return ($('#fErro').textContent = 'Indica a data de vencimento.');
  if (S.edit) enfileirar({ op: 'editar', id: S.edit.id, corpo });
  else enfileirar({ op: 'criar', cid: novoCid(), corpo });
  fecharSheet(); toast('Guardado');
  await aplicarAcao();
}

async function desfazerApagar(l) {
  const i = S.fila.findIndex((o) => o.op === 'apagar' && o.id === l.id);
  if (i >= 0) { S.fila.splice(i, 1); gravarFila(); }   // o apagar ainda não tinha saído: basta tirá-lo da fila
  else { const { id, categoria, ...resto } = l; enfileirar({ op: 'criar', cid: novoCid(), corpo: resto }); }
  await aplicarAcao();
}

async function apagarLancamento() {
  const l = S.edit; if (!l) return;
  enfileirar({ op: 'apagar', id: l.id });
  fecharSheet();
  toast('Lançamento apagado', { texto: 'Desfazer', fn: () => desfazerApagar(l) });
  await aplicarAcao();
}

/* ---------- Categorias ---------- */
async function guardarCategoria(id, campos) {
  try {
    const c = await api('PUT', `/financas/categorias/${id}`, campos);
    S.cats = S.cats.map((x) => (x.id === id ? c : x)); invalidarHistorico();
    await carregarMes({ silencioso: true }); renderCategorias();
  } catch (e) { toast(e.message); renderCategorias(); }
}

/* ---------- Ligações de eventos ---------- */
function ligar() {
  $('#mesAnt').innerHTML = ico('left'); $('#mesSeg').innerHTML = ico('right'); $('#btnRefresh').innerHTML = ico('refresh'); $('#fab').innerHTML = ico('plus');
  const abas = { lanc: ['list', 'Lançamentos'], resumo: ['wallet', 'Resumo'], rel: ['chart', 'Relatórios'], lemb: ['bell', 'Lembretes'], ajustes: ['gear', 'Ajustes'] };
  $$('nav.tabs button').forEach((b) => { const [i, t] = abas[b.dataset.tab]; b.innerHTML = ico(i) + `<span>${t}</span>`; b.onclick = () => mostrarTab(b.dataset.tab); });
  $('#versao').textContent = 'Finanças ' + APP_VERSION;
  const mudarMes = (n) => { S.mes = addMes(S.mes, n); S.preparado = null; S.resumoBase = null; S.resumo = null; carregarMes(); };
  $('#mesAnt').onclick = () => mudarMes(-1); $('#mesSeg').onclick = () => mudarMes(1);
  $('#btnRefresh').onclick = async () => { const b = $('#btnRefresh'); b.classList.add('spin'); invalidarHistorico(); await carregarMes({ silencioso: true }); b.classList.remove('spin'); };
  $('#fab').onclick = () => (S.tab === 'lemb' ? abrirSheetLemb(null) : abrirSheet(null));
  window.addEventListener('scroll', () => $('#topbar').classList.toggle('scrolled', window.scrollY > 4), { passive: true });

  document.addEventListener('click', (ev) => {
    const alvo = ev.target;
    const pagar = alvo.closest('[data-pagar]'); if (pagar) { ev.stopPropagation(); return alternarPago(idDe(pagar.dataset.pagar)); }
    const ir = alvo.closest('[data-ir]'); if (ir) return mostrarTab(ir.dataset.ir);
    if (alvo.closest('[data-fechar-prep]')) { try { localStorage.setItem('financas_prep_' + S.mes, '1'); } catch (e) { /* */ } return renderLancamentos(); }
    if (alvo.closest('[data-lemb-ativo]')) return;   // o interruptor trata-se no evento 'change'
    const lemb = alvo.closest('[data-lemb]'); if (lemb) { const id = +lemb.dataset.lemb; return abrirSheetLemb((S.lembretes || []).find((x) => x.id === id)); }
    const linha = alvo.closest('.row[data-id]');
    if (linha) { const id = idDe(linha.dataset.id); return abrirSheet(S.lancs.find((x) => x.id === id) || S.atrasados.find((x) => x.id === id)); }
  });
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && $('.sheet:not(.hidden)')) fecharSheet();
    if ((ev.key === 'Enter' || ev.key === ' ') && ev.target.matches && ev.target.matches('.row[data-id]')) { ev.preventDefault(); ev.target.click(); }
  });

  $$('[data-modo]').forEach((b) => b.onclick = () => { S.modo = b.dataset.modo; try { localStorage.setItem('financas_modo', S.modo); } catch (e) { /* */ } S.resumoBase = null; S.resumo = null; carregarResumo(); });
  $$('[data-rel]').forEach((b) => b.onclick = () => { S.rel = b.dataset.rel; renderRelatorio(); });
  $$('[data-tipo]').forEach((b) => b.onclick = () => { S.tipo = b.dataset.tipo; pintarTipo(); });
  $('#sheet').addEventListener('submit', guardarSheet);
  $$('[data-rep]').forEach((b) => b.onclick = () => { S.rep = b.dataset.rep; pintarRep(); });
  $('#lData').addEventListener('change', pintarRep);
  $('#sheetL').addEventListener('submit', guardarLembrete);
  $('#lCancelar').onclick = fecharSheet; $('#lApagar').onclick = apagarLembrete;
  $('#listaLemb').addEventListener('change', async (ev) => {
    const t = ev.target.closest('[data-lemb-ativo]'); if (!t) return;
    try { await api('PUT', `/financas/lembretes/${t.dataset.lembAtivo}`, { ativo: t.checked }); toast(t.checked ? 'Lembrete ativado' : 'Lembrete desativado'); await carregarLembretes(); }
    catch (e) { toast(e.message); t.checked = !t.checked; }
  });
  $('#fCancelar').onclick = fecharSheet; $('#scrim').onclick = fecharSheet; $('#fApagar').onclick = apagarLancamento;

  $('#btnNovaCat').onclick = async () => {
    const nome = $('#novaCat').value.trim(); if (!nome) return;
    try { const c = await api('POST', '/financas/categorias', { nome }); S.cats.push(c); $('#novaCat').value = ''; renderCategorias(); }
    catch (e) { toast(e.status === 409 ? 'Já existe uma categoria com esse nome.' : e.message); }
  };
  $('#listaCats').addEventListener('change', (ev) => {
    const linha = ev.target.closest('[data-cat]'); if (!linha) return; const id = +linha.dataset.cat;
    if (ev.target.matches('[data-cor]')) guardarCategoria(id, { cor: ev.target.value });
    if (ev.target.matches('[data-nome]')) { const n = ev.target.value.trim(); if (n) guardarCategoria(id, { nome: n }); else renderCategorias(); }
  });
  $('#listaCats').addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-apagar-cat]'); if (!b) return; const id = +b.closest('[data-cat]').dataset.cat;
    try { await api('DELETE', `/financas/categorias/${id}`); S.cats = S.cats.filter((c) => c.id !== id); renderCategorias(); toast('Categoria apagada'); }
    catch (e) { toast(e.status === 409 ? 'Categoria em uso: muda primeiro os lançamentos que a usam.' : e.message); }
  });
  $('#btnSair').onclick = () => {
    if (S.fila.length && !confirm(`Há ${S.fila.length} alteração(ões) por sincronizar. Se saíres agora perdem-se. Sair mesmo?`)) return;
    S.fila = []; gravarFila(); try { localStorage.removeItem(CACHE_KEY); } catch (e) { /* */ }
    const t = S.token; S.token = null; limparToken(); S.cats = [];
    if (t && window.google) { try { google.accounts.oauth2.revoke(t, () => {}); } catch (e) { /* */ } }
    $('#app').classList.add('hidden'); $('#login').classList.remove('hidden'); $('#loginStatus').textContent = '';
  };
  window.addEventListener('online', () => { if (S.token) carregarMes({ silencioso: true }); });
  window.addEventListener('offline', renderSync);
}

function entrar() {
  $('#login').classList.add('hidden'); $('#app').classList.remove('hidden');
  S.mes = S.mes || mesDe(hoje());
  mostrarTab(S.tab);
  carregarMes();
}

function arrancar() {
  S.fila = lerJson(FILA_KEY, []);
  ligar();
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
  $('#signinBtn').onclick = () => { if (S.tokenClient) S.tokenClient.requestAccessToken(); else $('#loginStatus').textContent = 'O início de sessão do Google ainda está a carregar…'; };
  // Com token válido a app abre logo (não espera pelo script do Google, que carrega em async).
  S.token = lerToken();
  if (S.token) entrar(); else $('#login').classList.remove('hidden');
  let tentativas = 0;
  (function esperar() {
    if (window.google && google.accounts) {
      iniciarGoogle();
      if (S.token) agendarRenovacao();
      // sem token: tenta uma renovação silenciosa (sessão Google ainda válida) antes de pedir o clique
      else renovarSilencioso().then((ok) => { if (ok) entrar(); });
    } else if (tentativas++ < 100) setTimeout(esperar, 100);
    else if (!S.token) $('#loginStatus').textContent = 'Falha ao carregar o início de sessão do Google. Recarrega a página.';
  })();
}

document.addEventListener('DOMContentLoaded', arrancar);
