import { defineConfig } from 'vitest/config'
import { loadEnv } from 'vite'
import react from '@vitejs/plugin-react'


// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '../', ['VITE_', 'ORCHESTRATOR_PORT'])
  const backendPort = env.ORCHESTRATOR_PORT || '9001'

  return {
    plugins: [react()],
    envDir: '../',
    envPrefix: ['VITE_', 'ORCHESTRATOR_PORT'],
    server: {
      proxy: {
        '/api': {
          target: `http://localhost:${backendPort}`,
          changeOrigin: true,
          ws: true,
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: true,
    },
  }
})
