import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/carga': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/almacen': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/entidades': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
