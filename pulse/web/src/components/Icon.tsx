import type { ReactNode } from 'react'

// Ícones lineares, traço 1,75, grelha 24. Sem emojis (CLAUDE.md).
const P: Record<string, ReactNode> = {
  mais: (<><rect x="4" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5" /><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5" /><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5" /></>),
  tarefas: (<><rect x="4" y="4" width="16" height="16" rx="3.5" /><path d="m8.5 12.2 2.6 2.6 4.6-5.2" /></>),
  calendario: (<><rect x="4" y="5.5" width="16" height="14.5" rx="3" /><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" /></>),
  email: (<><rect x="3.5" y="5.5" width="17" height="13" rx="3" /><path d="m4.5 8 7.5 5.5L19.5 8" /></>),
  bilhete: (<><rect x="6" y="3.5" width="12" height="13.5" rx="3.5" /><path d="M6 11h12M9 20.5l1.6-3.5M15 20.5 13.4 17" /><circle cx="9.3" cy="14" r=".6" /><circle cx="14.7" cy="14" r=".6" /></>),
  peso: (<><rect x="4" y="4.5" width="16" height="15" rx="4" /><path d="M8.5 9.5a4.2 4.2 0 0 1 7 0M12 9.6l1.6-1.3" /></>),
  rto: (<><rect x="5" y="3.5" width="14" height="17" rx="2.5" /><path d="M9 8h1.5M13.5 8H15M9 12h1.5M13.5 12H15M10 20.5v-4h4v4" /></>),
  financas: (<><path d="M4 8.5A2.5 2.5 0 0 1 6.5 6H18a2 2 0 0 1 2 2v9.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 17.5z" /><path d="M4 8.5V7a2 2 0 0 1 2-2h9M15.5 13.5h4.5" /></>),
  compras: (<><path d="M5 9h14l-1.3 9.2a2 2 0 0 1-2 1.8H8.3a2 2 0 0 1-2-1.8z" /><path d="M9 9V7a3 3 0 0 1 6 0v2" /></>),
  definicoes: (<><path d="M5 7h9M18 7h1M5 17h1M10 17h9" /><circle cx="16" cy="7" r="2" /><circle cx="8" cy="17" r="2" /></>),
  sair: (<><path d="M10 4.5H7a2.5 2.5 0 0 0-2.5 2.5v10A2.5 2.5 0 0 0 7 19.5h3M15 8l4 4-4 4M19 12H9.5" /></>),
  olho: (<><path d="M2.8 12S6 6.5 12 6.5 21.2 12 21.2 12 18 17.5 12 17.5 2.8 12 2.8 12z" /><circle cx="12" cy="12" r="2.7" /></>),
  'olho-off': (<><path d="M4 4l16 16M9.9 6.7A9 9 0 0 1 12 6.5c6 0 9.2 5.5 9.2 5.5a15 15 0 0 1-2.6 3.2M6.4 8.4A15 15 0 0 0 2.8 12S6 17.5 12 17.5c1.3 0 2.5-.3 3.5-.7M10 10a2.7 2.7 0 0 0 3.9 3.5" /></>),
  alerta: (<><path d="M12 4.2 21 19.5H3z" /><path d="M12 10v4.2M12 16.9v.1" /></>),
  info: (<><circle cx="12" cy="12" r="8.5" /><path d="M12 11v5M12 8v.1" /></>),
  certo: (<><path d="m5 12.5 4.5 4.5L19 7.5" /></>),
  ponto: (<><circle cx="12" cy="12" r="3" /></>),
  seta: (<><path d="M5 12h14M13 6l6 6-6 6" /></>),
  voltar: (<><path d="M19 12H5M11 6l-6 6 6 6" /></>),
  chave: (<><circle cx="8" cy="15" r="3.5" /><path d="m10.5 12.5 8-8M15.5 7.5l2.5 2.5M13 10l2 2" /></>),
  dispositivo: (<><rect x="7" y="3.5" width="10" height="17" rx="2.5" /><path d="M11 17.5h2" /></>),
  ligacao: (<><path d="M4 9a12 12 0 0 1 16 0M7 12.5a8 8 0 0 1 10 0M10 16a4 4 0 0 1 4 0M12 19.5v.1" /></>),
}

export type IconName = keyof typeof P

export function Icon({ nome, tamanho = 24, titulo }: { nome: IconName; tamanho?: number; titulo?: string }) {
  return (
    <svg width={tamanho} height={tamanho} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" role={titulo ? 'img' : undefined} aria-label={titulo} aria-hidden={titulo ? undefined : true}>
      {P[nome]}
    </svg>
  )
}
