import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Always port 5173: the backend only allows this address (CORS). If 5173 is busy,
    // Vite stops with a clear error instead of quietly moving to another port.
    port: 5173,
    strictPort: true,
  },
})
