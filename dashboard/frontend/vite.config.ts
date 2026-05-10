import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// During `vite dev`, proxy /api/* and /healthz to the FastAPI backend running
// on port 8002 (the dashboard's default). The frontend served by vite dev
// runs on port 5173.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8002',
      '/healthz': 'http://127.0.0.1:8002',
      '/readyz': 'http://127.0.0.1:8002',
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // Lazy-load the charting bundle so the initial paint stays light.
        manualChunks: {
          charts: ['apexcharts', 'react-apexcharts'],
          markdown: ['react-markdown', 'remark-gfm'],
        },
      },
    },
  },
});
