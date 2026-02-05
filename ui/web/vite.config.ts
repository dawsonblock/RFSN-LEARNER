import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev proxy so the frontend can use fetch('/api/...') and ws://host/ws/...
// while running on :5173, proxying to FastAPI on :8081
export default defineConfig({
    plugins: [react()],
    server: {
        port: 5173,
        proxy: {
            '/api': {
                target: 'http://localhost:8080',
                changeOrigin: true,
            },
            '/ws': {
                target: 'ws://localhost:8080',
                ws: true,
                changeOrigin: true,
            },
        },
    },
})
