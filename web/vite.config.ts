import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Built output is committed to ../public, which Vercel serves as static files
// next to the Python API. CI rebuilds it and fails if it differs.
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: {
    outDir: '../public',
    emptyOutDir: true,
    sourcemap: false,
    // One stable chunk name per file keeps diffs of the committed build readable.
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name]-[hash].js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
});
