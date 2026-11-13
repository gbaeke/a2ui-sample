import react from '@vitejs/plugin-react';
import {defineConfig} from 'vite';

import {a2aMiddleware} from './middleware/a2a';

export default defineConfig({
  plugins: [react(), a2aMiddleware()],
  server: {
    port: 5173,
    strictPort: true,
    // The shared catalog lives one level up, next to the agent.
    fs: {allow: ['..']},
  },
});
