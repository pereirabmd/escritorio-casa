import '@fontsource-variable/inter'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { aplicarTema, lerTema } from './lib/theme'
import { vigiarTeclado } from './lib/teclado'
import './styles/tokens.css'
import './styles/base.css'
import './styles/layout.css'

aplicarTema(lerTema())
vigiarTeclado()
createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
