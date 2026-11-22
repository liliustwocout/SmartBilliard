import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Phòng quản lý: cổng web 5174, API 8100 (phòng demo dùng 5173/8000).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5174, strictPort: true, proxy: { '/api': 'http://127.0.0.1:8100' } },
});
