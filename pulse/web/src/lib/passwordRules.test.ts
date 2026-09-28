import { regras, todasOk } from './passwordRules'

const E = 'pereirabmd@gmail.com'
const ok = (nova: string, atual = 'antiga-1234') => todasOk(regras(nova, atual, E))

test('aceita uma palavra-passe boa', () => expect(ok('Outra-Palavra-Segura-7')).toBe(true))

test('recusa curta, repetitiva, previsível e igual à atual', () => {
  expect(ok('Curta1')).toBe(false)
  expect(ok('aaaaaaaaaaaa')).toBe(false)
  expect(ok('1234567890')).toBe(false)
  expect(ok(E)).toBe(false)
  expect(ok('pereirabmd')).toBe(false)
  expect(ok('Mesma-Palavra-1', 'Mesma-Palavra-1')).toBe(false)
})

test('vazia não cumpre nenhuma regra', () => {
  expect(regras('', '', E).every((r) => !r.ok)).toBe(true)
})
