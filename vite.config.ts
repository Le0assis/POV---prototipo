import { cpSync } from 'node:fs';
import { resolve } from 'node:path';
import preact from '@preact/preset-vite';
import { defineConfig } from 'vitest/config';

const frontend = resolve(__dirname, 'frontend');

export default defineConfig({
  root: frontend,
  base: '/',
  publicDir: 'public',
  plugins: [
    preact(),
    {
      name: 'copy-leaflet',
      apply: 'build',
      closeBundle() {
        cpSync(resolve(frontend, 'vendor/leaflet'), resolve(frontend, 'dist/vendor/leaflet'), {
          recursive: true
        });
      }
    }
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolve(frontend, 'index.html'),
        viewer: resolve(frontend, 'viewer.html'),
        locate: resolve(frontend, 'locate.html'),
        admin: resolve(frontend, 'admin/index.html'),
        editor: resolve(frontend, 'admin/editor.html'),
        recorder: resolve(frontend, 'admin/recorder.html'),
        mapConfig: resolve(frontend, 'admin/map-config.html'),
        qrcodes: resolve(frontend, 'admin/qrcodes.html')
      }
    }
  },
  test: {
    environment: 'node',
    include: ['tests/**/*.test.js'],
    exclude: ['dist/**', 'vendor/**', 'node_modules/**'],
    testTimeout: 120000,
    hookTimeout: 120000
  }
});
