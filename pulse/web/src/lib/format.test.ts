import { fmtDiaCurto, fmtDias, fmtDataIso, fmtDiaMes, fmtEuro, fmtPeso, plural, saudacao } from './format'

test('moeda e peso no formato pt-PT do Design System', () => {
  expect(fmtEuro(1245.5).replace(/\s/g, ' ')).toBe('1 245,50 €')
  expect(fmtEuro(20).replace(/\s/g, ' ')).toBe('20,00 €')
  expect(fmtPeso(104.8)).toBe('104,8 kg')
  expect(fmtPeso(80)).toBe('80,0 kg')
})

test('datas', () => {
  expect(fmtDataIso('2026-09-28')).toBe('28/09/2026')
  expect(fmtDataIso('2026-09-28 07:30:00')).toBe('28/09/2026')
  expect(fmtDiaMes('2026-09-28')).toBe('28 de setembro')
})

test('dias relativos', () => {
  expect([0, 1, -1, 5, -3].map(fmtDias)).toEqual(['hoje', 'amanhã', 'ontem', 'em 5 dias', 'há 3 dias'])
})

test('plural e saudação', () => {
  expect(plural(1, 'dia', 'dias')).toBe('1 dia')
  expect(plural(3, 'dia', 'dias')).toBe('3 dias')
  const h = (n: number) => saudacao(new Date(2026, 8, 30, n))
  expect([h(2), h(9), h(15), h(22)]).toEqual(['Boa noite', 'Bom dia', 'Boa tarde', 'Boa noite'])
})

describe('fmtDiaCurto', () => {
  const agora = new Date(2026, 8, 30, 10, 0)
  test('hoje, amanhã e uma data mais à frente', () => {
    expect(fmtDiaCurto('2026-09-30', agora)).toBe('Hoje')
    expect(fmtDiaCurto('2026-10-01', agora)).toBe('Amanhã')
    expect(fmtDiaCurto('2026-10-02', agora)).toBe('sex, 2 out')
  })
})
