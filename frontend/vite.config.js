import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Frontend dev server runs on :5173 (allowed by backend CORS by default).
// The API base URL comes from VITE_API_BASE_URL (see .env.example).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  preview: {
    port: 4173,
  },
});
