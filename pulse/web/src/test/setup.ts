import '@testing-library/jest-dom/vitest'
import { afterEach } from 'vitest'
import { esquecerUltimoHoje } from '../lib/useHoje'
import { cleanup } from '@testing-library/react'

afterEach(() => { cleanup(); esquecerUltimoHoje() })
