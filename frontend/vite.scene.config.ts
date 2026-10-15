import { resolve } from 'path'
import { defineConfig } from 'vite'

export default defineConfig({
  publicDir: false,
  build: {
    lib: {
      entry: resolve(__dirname, 'src/ui/scene-runtime/index.ts'),
      name: 'NexusScene',
      formats: ['iife'],
      fileName: () => 'runtime.js',
    },
    outDir: 'public/scene',
    emptyOutDir: true,
    minify: 'esbuild',
    rollupOptions: {
      output: {
        exports: 'named',
        banner: '/*! Three.js (MIT License) & NexusScene Runtime */',
      },
    },
  },
})
