import { defineConfig } from 'vite';

export default defineConfig({
  root: 'src',
  base: process.env.ONX_WEB_UI_BASE || '/',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      input: 'src/index.html',
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.ONX_DEV_API || 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
