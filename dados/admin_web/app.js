'use strict';
// Consulta e edição das bases SQLite do Pi (ver admin_db.py). Todo o texto vindo da base entra por textContent/value: nunca innerHTML.
const $ = (id) => document.getElementById(id);
const estado = { csrf: null, db: null, esquema: [], tabela: null, pagina: 1, tamanho: 50, ordem: null, sentido: 'asc', q: '', dados: null };
const MASCARA = '••••••••';

function toast(msg) {
  const t = $('toast'); t.textContent = msg; t.classList.add('ver');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('ver'), 2800);
}

async function api(metodo, caminho, corpo) {
  const opts = { method: metodo, headers: {}, credentials: 'same-origin' };
  if (corpo !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(corpo); }
  if (metodo !== 'GET') opts.headers['X-CSRF'] = estado.csrf || '';
  const r = await fetch(caminho, opts);
  let d = null; try { d = await r.json(); } catch (e) { /* sem corpo */ }
  if (r.status === 401 && caminho !== '/api/login') { mostrarLogin(); throw new Error('sessão expirada'); }
  if (!r.ok) throw new Error((d && d.erro) || ('erro ' + r.status));
  return d;
}

function el(tag, props, ...filhos) {
  const e = document.createElement(tag);
  Object.entries(props || {}).forEach(([k, v]) => { if (k === 'class') e.className = v; else if (k in e) e[k] = v; else e.setAttribute(k, v); });
  filhos.flat().forEach(f => e.append(f instanceof Node ? f : document.createTextNode(String(f))));
  return e;
}

// ---------------- login / sessão ----------------
function mostrarLogin() { $('app').hidden = true; $('login').hidden = false; $('pw').value = ''; $('pw').focus(); }
async function entrar(dados) {
  estado.csrf = dados.csrf;
  $('login').hidden = true; $('app').hidden = false;
  const sel = $('sel-db'); sel.replaceChildren(...dados.bases.map(b => el('option', { value: b, textContent: b })));
  estado.db = dados.bases[0]; sel.value = estado.db;
  $('aviso').hidden = false;
  $('aviso').textContent = '⚠️ Edição direta na base: as apps têm regras próprias (ids, datas, estados). As restrições da base recusam o inválido e tudo fica registado e reversível na aba «Alterações».';
  await carregarEsquema();
}
$('form-login').addEventListener('submit', async (ev) => {
  ev.preventDefault(); $('erro-login').textContent = '';
  try { await entrar(await api('POST', '/api/login', { password: $('pw').value })); }
  catch (e) { $('erro-login').textContent = e.message; }
});
$('sair').addEventListener('click', async () => { try { await api('POST', '/api/logout', {}); } catch (e) { /* ok */ } mostrarLogin(); });
$('sel-db').addEventListener('change', async () => { estado.db = $('sel-db').value; estado.tabela = null; await carregarEsquema(); });

// ---------------- abas ----------------
document.querySelectorAll('#abas button').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('#abas button').forEach(x => x.classList.toggle('ativa', x === b));
  document.querySelectorAll('.aba').forEach(a => { a.hidden = a.id !== 'aba-' + b.dataset.aba; });
  if (b.dataset.aba === 'alteracoes') carregarAlteracoes();
  if (b.dataset.aba === 'backup') carregarBackup();
}));

// ---------------- tabelas ----------------
async function carregarEsquema() {
  const d = await api('GET', '/api/esquema?db=' + encodeURIComponent(estado.db));
  estado.esquema = d.tabelas;
  const lista = $('lista-tabelas');
  lista.replaceChildren(...d.tabelas.map(t => {
    const b = el('button', { class: t.nome === estado.tabela ? 'ativa' : '' }, el('span', {}, t.nome), el('span', { class: 'n' }, t.linhas));
    b.addEventListener('click', () => escolherTabela(t.nome));
    return b;
  }));
  $('vazio').hidden = !!estado.tabela; $('tabela-vista').hidden = !estado.tabela;
  if (estado.tabela) await carregarLinhas();
}
async function escolherTabela(nome) {
  estado.tabela = nome; estado.pagina = 1; estado.ordem = null; estado.sentido = 'asc'; estado.q = ''; $('pesquisa').value = '';
  $('esquema').hidden = true;
  await carregarEsquema();
}
function tabelaAtual() { return estado.esquema.find(t => t.nome === estado.tabela); }

async function carregarLinhas() {
  const p = new URLSearchParams({ db: estado.db, tabela: estado.tabela, pagina: estado.pagina, tamanho: estado.tamanho, q: estado.q });
  if (estado.ordem) { p.set('ordem', estado.ordem); p.set('sentido', estado.sentido); }
  const d = await api('GET', '/api/linhas?' + p);
  estado.dados = d;
  $('titulo-tabela').textContent = estado.tabela + ' (' + d.total + ')';
  $('esquema').textContent = tabelaAtual().sql;
  const grelha = $('grelha');
  const cab = el('tr', {}, d.colunas.map(c => {
    const seta = estado.ordem === c.nome ? (estado.sentido === 'asc' ? ' ▲' : ' ▼') : '';
    const th = el('th', { title: c.tipo + (c.pk ? ' · chave' : '') + (c.obrigatoria ? ' · obrigatória' : '') }, c.nome + seta);
    th.addEventListener('click', () => {
      estado.sentido = (estado.ordem === c.nome && estado.sentido === 'asc') ? 'desc' : 'asc'; estado.ordem = c.nome; estado.pagina = 1; carregarLinhas();
    });
    return th;
  }));
  const corpo = d.linhas.map(l => {
    const tr = el('tr', {}, d.colunas.map(c => {
      const v = l[c.nome];
      const td = el('td', { class: v === null ? 'nulo' : (v === MASCARA ? 'seg' : '') }, v === null ? 'NULL' : String(v));
      if (typeof v === 'string' && v.length > 40) td.title = v.slice(0, 500);
      return td;
    }));
    tr.addEventListener('click', () => abrirEditor(l));
    return tr;
  });
  grelha.replaceChildren(el('thead', {}, cab), el('tbody', {}, corpo));
  const paginas = Math.max(1, Math.ceil(d.total / d.tamanho));
  $('paginacao').textContent = `página ${d.pagina} de ${paginas}`;
  $('ant').disabled = d.pagina <= 1; $('seg').disabled = d.pagina >= paginas;
}
$('ant').addEventListener('click', () => { estado.pagina--; carregarLinhas(); });
$('seg').addEventListener('click', () => { estado.pagina++; carregarLinhas(); });
$('tamanho').addEventListener('change', () => { estado.tamanho = Number($('tamanho').value); estado.pagina = 1; carregarLinhas(); });
$('ver-esquema').addEventListener('click', () => { $('esquema').hidden = !$('esquema').hidden; });
let _busca; $('pesquisa').addEventListener('input', () => { clearTimeout(_busca); _busca = setTimeout(() => { estado.q = $('pesquisa').value; estado.pagina = 1; carregarLinhas(); }, 300); });

// ---------------- editor de linha ----------------
let linhaEmEdicao = null;   // null = nova linha
function campoInput(col, valor, nova) {
  const tipo = col.tipo;
  const numerico = /INT|REAL|FLOA|DOUB/.test(tipo);
  const protegido = valor === MASCARA;
  const longo = typeof valor === 'string' && (valor.length > 60 || valor.includes('\n'));
  const entrada = longo ? el('textarea', { rows: 4 }) : el('input', { type: 'text', inputMode: numerico ? 'decimal' : 'text' });
  entrada.value = valor === null || valor === undefined ? '' : String(valor);
  entrada.dataset.col = col.nome;
  const nulo = el('input', { type: 'checkbox' });
  nulo.checked = valor === null || (nova && col.por_omissao === null && !col.obrigatoria);
  const podeNulo = !col.obrigatoria;
  if (protegido) { entrada.disabled = true; nulo.disabled = true; }
  const linha = el('div', { class: 'linha' }, entrada, podeNulo && !protegido ? el('label', {}, nulo, ' NULL') : '');
  const meta = `${col.tipo || 'sem tipo'}${col.pk ? ' · chave' : ''}${col.obrigatoria ? ' · obrigatória' : ''}${col.por_omissao !== null ? ' · omissão ' + col.por_omissao : ''}${protegido ? ' · segredo: não se edita' : ''}`;
  const bloco = el('div', { class: 'campo' }, el('label', {}, col.nome), linha, el('div', { class: 'meta' }, meta));
  bloco._ler = () => (nulo.checked && podeNulo) ? null : entrada.value;
  bloco._alterado = () => {
    if (protegido) return false;
    const orig = (valor === undefined) ? null : valor, atual = bloco._ler();
    return (orig === null) !== (atual === null) || (orig !== null && String(orig) !== atual);
  };
  entrada.addEventListener('input', () => { nulo.checked = false; });
  return bloco;
}
function abrirEditor(linha) {
  linhaEmEdicao = linha; const t = tabelaAtual(); const nova = linha === null;
  $('dlg-titulo').textContent = (nova ? 'Nova linha em ' : 'Editar linha em ') + t.nome + (nova ? '' : ` (rowid ${linha._rowid_})`);
  $('dlg-erro').textContent = '';
  const blocos = t.colunas.map(c => campoInput(c, nova ? null : linha[c.nome], nova));
  $('campos').replaceChildren(...blocos); $('campos')._blocos = blocos;
  $('dlg-apagar').hidden = nova;
  if (!$('dlg').open) $('dlg').showModal();
}
$('nova-linha').addEventListener('click', () => abrirEditor(null));
$('dlg-cancelar').addEventListener('click', () => $('dlg').close());
$('form-linha').addEventListener('submit', async (ev) => {
  ev.preventDefault(); $('dlg-erro').textContent = '';
  const t = tabelaAtual(); const blocos = $('campos')._blocos; const valores = {};
  blocos.forEach((b, i) => {
    const c = t.colunas[i]; const v = b._ler();
    if (linhaEmEdicao === null) { if (v !== null && !(v === '' && c.por_omissao !== null) && !(v === '' && c.pk)) valores[c.nome] = v; }
    else if (b._alterado()) valores[c.nome] = v;
  });
  try {
    if (linhaEmEdicao === null) { await api('POST', '/api/linha', { db: estado.db, tabela: estado.tabela, valores }); toast('Linha criada'); }
    else if (Object.keys(valores).length) { await api('PUT', '/api/linha', { db: estado.db, tabela: estado.tabela, rowid: linhaEmEdicao._rowid_, valores }); toast('Guardado'); }
    else { $('dlg').close(); return; }
    $('dlg').close(); await carregarEsquema();
  } catch (e) { $('dlg-erro').textContent = e.message; }
});
$('dlg-apagar').addEventListener('click', async () => {
  if (!confirm('Apagar esta linha? (fica registado e pode ser revertido em «Alterações»)')) return;
  try { await api('DELETE', `/api/linha?db=${encodeURIComponent(estado.db)}&tabela=${encodeURIComponent(estado.tabela)}&rowid=${linhaEmEdicao._rowid_}`); toast('Linha apagada'); $('dlg').close(); await carregarEsquema(); }
  catch (e) { $('dlg-erro').textContent = e.message; }
});

// ---------------- SQL ----------------
$('correr-sql').addEventListener('click', async () => {
  $('sql-info').textContent = 'a correr…';
  try {
    const d = await api('POST', '/api/sql', { db: estado.db, sql: $('sql').value });
    $('grelha-sql').replaceChildren(el('thead', {}, el('tr', {}, d.colunas.map(c => el('th', {}, c)))),
      el('tbody', {}, d.linhas.map(l => el('tr', {}, l.map(v => el('td', { class: v === null ? 'nulo' : '' }, v === null ? 'NULL' : String(v)))))));
    $('sql-info').textContent = d.linhas.length + ' linha(s)' + (d.truncado ? ' (truncado a 500)' : '');
  } catch (e) { $('sql-info').textContent = '❌ ' + e.message; }
});

// ---------------- alterações ----------------
async function carregarAlteracoes() {
  const d = await api('GET', '/api/alteracoes');
  const resumo = (v) => v === null ? '—' : JSON.stringify(v);
  $('grelha-alt').replaceChildren(
    el('thead', {}, el('tr', {}, ['#', 'Quando', 'Base', 'Tabela', 'Op', 'rowid', 'Antes', 'Depois', ''].map(h => el('th', {}, h)))),
    el('tbody', {}, d.alteracoes.map(a => {
      const b = el('button', { class: 'sec', textContent: 'Reverter', disabled: a.revertida || a.op === 'reverter' });
      b.addEventListener('click', async () => { try { await api('POST', '/api/reverter', { id: a.id }); toast('Revertida'); carregarAlteracoes(); } catch (e) { toast(e.message); } });
      return el('tr', {}, el('td', {}, a.id), el('td', {}, a.ts), el('td', {}, a.base), el('td', {}, a.tabela), el('td', {}, a.op + (a.revertida ? ' (revertida)' : '')),
        el('td', {}, a.rowid), el('td', { title: resumo(a.antes) }, resumo(a.antes)), el('td', { title: resumo(a.depois) }, resumo(a.depois)), el('td', {}, b));
    })));
  $('grelha-snap').replaceChildren(el('thead', {}, el('tr', {}, ['Ficheiro', 'Quando', 'Bytes'].map(h => el('th', {}, h)))),
    el('tbody', {}, d.snapshots.map(s => el('tr', {}, el('td', {}, s.ficheiro), el('td', {}, s.quando), el('td', {}, s.bytes)))));
}

// ---------------- backup ----------------
async function carregarBackup() {
  const d = await api('GET', '/api/backup');
  $('info-backup').replaceChildren(
    el('div', {}, el('strong', {}, 'Repositório: '), d.repositorio),
    el('div', {}, el('strong', {}, 'Último backup: '), d.ultimo ? `${d.ultimo.replace('T', ' ').slice(0, 19)} (commit ${d.commit})` : 'sem informação'),
    el('div', {}, el('strong', {}, 'Ficheiros: '), d.ficheiros.map(f => `${f.nome} (${f.bytes} B)`).join(', ') || '—'));
}
$('backup-agora').addEventListener('click', async () => {
  $('backup-agora').disabled = true; $('saida-backup').hidden = false; $('saida-backup').textContent = 'a fazer backup…';
  try { const d = await api('POST', '/api/backup/correr', { forcar: $('backup-forcar').checked }); $('saida-backup').textContent = (d.ok ? '✅ ' : '❌ ') + d.saida; carregarBackup(); }
  catch (e) { $('saida-backup').textContent = '❌ ' + e.message; }
  finally { $('backup-agora').disabled = false; }
});

// ---------------- arranque ----------------
(async () => {
  try { await entrar(await api('GET', '/api/sessao')); } catch (e) { mostrarLogin(); }
})();
