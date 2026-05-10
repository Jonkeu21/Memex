import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'node:path';

// Vitest config lives alongside vite.config.ts so node_modules resolution
// remains rooted at frontend/, but the include + setup paths reach up into
// dashboard/tests/frontend/ where the smoke tests are kept (per the prompt's
// expected file layout).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Helpful absolute alias so test files don't have to walk ../../frontend/src.
      '@app': resolve(__dirname, 'src'),
    },
    // Test files live at dashboard/tests/frontend/ but should resolve modules
    // from frontend/node_modules.
    preserveSymlinks: false,
  },
  optimizeDeps: {
    include: ['react', 'react-dom', 'react-router-dom', '@mui/material'],
  },
  server: {
    fs: {
      // Allow vite to read setup + tests from dashboard/tests/frontend.
      allow: [resolve(__dirname, '..')],
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: [resolve(__dirname, '../tests/frontend/setup.ts')],
    include: [resolve(__dirname, '../tests/frontend/**/*.test.{ts,tsx}')],
    css: false,
    server: {
      deps: {
        inline: [/@mui\//, /@emotion\//],
      },
    },
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx', 'src/types/**'],
      thresholds: {
        lines: 50,
        functions: 50,
        branches: 50,
        statements: 50,
      },
    },
  },
});
