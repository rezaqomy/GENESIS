import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, strictPort: true, proxy: {
    '/api': { target: process.env.BACKEND_URL || 'http://127.0.0.1:8000' },
    '/health': { target: process.env.BACKEND_URL || 'http://127.0.0.1:8000' },
    '/ws': { target: process.env.BACKEND_URL || 'http://127.0.0.1:8000', ws: true },
  } },
})
