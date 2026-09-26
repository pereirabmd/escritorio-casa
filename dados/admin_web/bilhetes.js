'use strict';
// Página de administração dos utilizadores do bilhetes_cp (só LAN). Sem innerHTML com dados: tudo por textContent.
const $ = (id) => document.getElementById(id);
let csrf = '', utilizadores = [], editar = null;   // editar: id em edição, ou 'novo'

function el(tag, attrs = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  for (const f of filhos.flat()) if (f !== null && f !== undefined) e.append(f instanceof Node ? f : document.createTextNode(String(f)));
  return e;
}
function toast(m) { const t = $('toast'); t.textContent = m; t.classList.add('ver'); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('ver'), 3000); }

async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, { method: metodo, credentials: 'same-origin',
    headers: { ...(corpo !== undefined ? { 'Content-Type': 'application/json' } : {}), ...(metodo !== 'GET' ? { 'X-CSRF': csrf } : {}) },
    body: corpo !== undefined ? JSON.stringify(corpo) : undefined });
  let d = null; try { d = await r.json(); } catch (e) { /* sem corpo */ }
  if (r.status === 401 && caminho !== '/api/login') { mostrarLogin(); throw new Error('sessão expirada'); }
  if (!r.ok) throw new Error((d && d.erro) || ('erro ' + r.status));
  return d;
}

function mostrarLogin() { $('app').hidden = true; $('login').hidden = false; $('pw').value = ''; $('pw').focus(); }
async function entrar(d) { csrf = d.csrf; $('login').hidden = true; $('app').hidden = false; await carregar(); }
$('form-login').addEventListener('submit', async (ev) => {
  ev.preventDefault(); $('erro-login').textContent = '';
  try { await entrar(await api('POST', '/api/login', { password: $('pw').value })); } catch (e) { $('erro-login').textContent = e.message; }
});

const marca = (ok, texto) => el('span', { class: ok ? '' : 'mut' }, (ok ? '✓ ' : '✗ ') + texto);

async function carregar() {
  const d = await api('GET', '/api/bilhetes/utilizadores');
  utilizadores = d.utilizadores;
  $('aviso-chave').hidden = d.chave_configurada;
  $('lista').replaceChildren(...utilizadores.map((u) => {
    const cartao = el('div', { class: 'cartao util' + (u.ativo ? '' : ' inativo') },
      el('div', { class: 'util-topo' },
        el('strong', {}, u.nome), u.admin ? el('span', { class: 'etiqueta' }, 'admin') : null, u.ativo ? null : el('span', { class: 'etiqueta' }, 'inativo'),
        el('span', { class: 'esp' }), el('button', { class: 'sec' }, 'Editar')),
      el('div', { class: 'mut' }, u.email ? 'Login: ' + u.email : 'Sem login próprio (marca-se por ele)'),
      el('div', { class: 'marcas' }, marca(!!u.cp_email, 'e-mail CP'), marca(u.cp_password_definida, 'password CP'), marca(!!u.passageiro_cc, 'CC'),
        marca(!!u.nif, 'NIF'), marca(!!u.passe_verde_numero, 'Passe Verde'),
        u.passe_data_ultima_compra ? el('span', { class: 'mut' }, 'passe carregado a ' + u.passe_data_ultima_compra) : null));
    cartao.querySelector('button').addEventListener('click', () => abrir(u));
    return cartao;
  }));
}

const CAMPOS_TEXTO = ['nome', 'email', 'cp_email', 'passageiro_nome', 'passageiro_cc', 'passageiro_telemovel', 'nif', 'passe_verde_numero', 'passe_data_ultima_compra'];

function abrir(u) {
  editar = u ? u.id : 'novo';
  $('dlg-titulo').textContent = u ? 'Editar ' + u.nome : 'Novo utilizador';
  for (const c of CAMPOS_TEXTO) $('f-' + c).value = (u && u[c]) || '';
  $('f-admin').checked = !!(u && u.admin); $('f-ativo').checked = u ? !!u.ativo : true;
  $('f-passe_validade_dias').value = u ? u.passe_validade_dias : 29;
  $('f-password').value = ''; $('f-limpar').checked = false;
  $('f-password').placeholder = u && u.cp_password_definida ? '•••••••• (guardada; deixa vazio para manter)' : 'ainda sem password';
  $('linha-limpar').hidden = !(u && u.cp_password_definida);
  $('apagar').hidden = !u || u.id === 1;
  $('f-admin').disabled = $('f-ativo').disabled = !!(u && u.id === 1);
  $('erro-util').textContent = '';
  $('dlg').showModal();
}

$('novo').addEventListener('click', () => abrir(null));
$('cancelar').addEventListener('click', () => $('dlg').close());

$('form-util').addEventListener('submit', async (ev) => {
  ev.preventDefault(); $('erro-util').textContent = '';
  const corpo = { admin: $('f-admin').checked, ativo: $('f-ativo').checked, passe_validade_dias: Number($('f-passe_validade_dias').value) };
  for (const c of CAMPOS_TEXTO) corpo[c] = $('f-' + c).value;
  if ($('f-password').value) corpo.password = $('f-password').value;
  if ($('f-limpar').checked) corpo.limpar_password = true;
  $('guardar').disabled = true;
  try {
    if (editar === 'novo') await api('POST', '/api/bilhetes/utilizadores', corpo);
    else await api('PUT', '/api/bilhetes/utilizadores/' + editar, corpo);
    $('f-password').value = ''; $('dlg').close(); toast('Guardado'); await carregar();
  } catch (e) { $('erro-util').textContent = e.message; } finally { $('guardar').disabled = false; }
});

$('apagar').addEventListener('click', async () => {
  const u = utilizadores.find((x) => x.id === editar);
  if (!u || !confirm('Apagar ' + u.nome + '? Só é possível se não tiver viagens, pedidos nem compras.')) return;
  try { await api('DELETE', '/api/bilhetes/utilizadores/' + u.id); $('dlg').close(); toast('Apagado'); await carregar(); }
  catch (e) { $('erro-util').textContent = e.message; }
});

(async () => { try { await entrar(await api('GET', '/api/sessao')); } catch (e) { mostrarLogin(); } })();
