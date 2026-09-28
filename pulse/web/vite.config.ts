/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// A Web vive em https://bmdpereira.duckdns.org/pulse/ e a API em /pulse/api/ (mesma origem: o cookie de sessão é httpOnly).
export default defineConfig({
  base: '/pulse/',
  plugins: [react()],
  server: { port: 5173, proxy: { '/pulse/api': { target: 'http://127.0.0.1:8897', rewrite: (p) => p.replace(/^\/pulse/, '') } } },
  build: { sourcemap: false, target: 'es2022' },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], globals: true, css: false },
})
