import { api, ApiError, definirAoPerderSessao, mensagemDeErro } from './client'
import { servidorFalso } from '../test/api-mock'

afterEach(() => { vi.unstubAllGlobals(); definirAoPerderSessao(null) })

test('envia credenciais da mesma origem e o cabeçalho anti-CSRF', async () => {
  const { pedidos } = servidorFalso({ 'POST /auth/logout': () => [200, { ok: true }] })
  await api.post('/auth/logout')
  expect(pedidos[0].cabecalhos['X-Pulse-Client']).toBe('web')
  expect(vi.mocked(fetch).mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', method: 'POST' })
})

test('erro do servidor vira ApiError com código e mensagem', async () => {
  servidorFalso({ 'GET /x': () => [409, { erro: { codigo: 'conflito', mensagem: 'já existe' } }] })
  await expect(api.get('/x')).rejects.toMatchObject({ status: 409, codigo: 'conflito', message: 'já existe' })
})

test('falha de rede é ApiError 0 «rede»', async () => {
  servidorFalso({ 'GET /x': () => new Error('boom') })
  const e = await api.get('/x').catch((x) => x)
  expect(e).toBeInstanceOf(ApiError)
  expect(e).toMatchObject({ status: 0, codigo: 'rede' })
})

test('só «nao_autenticado» avisa que a sessão acabou (não o login, nem uma password atual errada)', async () => {
  const perdeu = vi.fn()
  definirAoPerderSessao(perdeu)
  servidorFalso({ 'GET /dashboard/today': () => [401, { erro: { codigo: 'nao_autenticado', mensagem: 'x' } }],
    'POST /auth/login': () => [401, { erro: { codigo: 'credenciais_invalidas', mensagem: 'x' } }],
    'POST /auth/password': () => [401, { erro: { codigo: 'password_atual_errada', mensagem: 'x' } }],
    'GET /auth/me': () => [401, { erro: { codigo: 'nao_autenticado', mensagem: 'x' } }] })
  await api.post('/auth/login', {}).catch(() => 0)
  await api.post('/auth/password', {}).catch(() => 0)
  await api.get('/auth/me').catch(() => 0)
  expect(perdeu).not.toHaveBeenCalled()
  await api.get('/dashboard/today').catch(() => 0)
  expect(perdeu).toHaveBeenCalledTimes(1)
})

test('mensagens em pt-PT para os códigos conhecidos', () => {
  const e = (codigo: string, status = 400) => new ApiError(status, codigo, 'orig')
  expect(mensagemDeErro(e('credenciais_invalidas', 401))).toBe('E-mail ou palavra-passe incorretos.')
  expect(mensagemDeErro(e('conta_bloqueada', 429))).toMatch(/Demasiadas tentativas/)
  expect(mensagemDeErro(e('password_atual_errada', 401))).toMatch(/atual não está certa/)
  expect(mensagemDeErro(e('erro_interno', 500))).toMatch(/servidor/)
  expect(mensagemDeErro(new Error('x'))).toMatch(/inesperado/)
})
