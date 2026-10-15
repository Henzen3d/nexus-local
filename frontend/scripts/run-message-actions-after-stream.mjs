import { build } from 'esbuild'
import { mkdtemp, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const dir = await mkdtemp(resolve('node_modules/.message-actions-after-stream-'))
try {
  const outfile = resolve(dir, 'actions.mjs')
  await build({
    entryPoints: ['scripts/message-actions-after-stream.tsx'],
    outfile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    jsx: 'automatic',
    define: {
      'import.meta.env.VITE_API_URL': 'undefined',
      'import.meta.env.VITE_WS_URL': 'undefined',
      'import.meta.env.DEV': 'false',
    },
    plugins: [{
      name: 'ignore-css',
      setup(b) {
        b.onResolve({ filter: /\.css$/ }, (args) => ({ path: args.path, namespace: 'css-stub' }))
        b.onLoad({ filter: /.*/, namespace: 'css-stub' }, () => ({ contents: '', loader: 'js' }))
      },
    }],
  })
  await import(pathToFileURL(outfile).href)
} finally {
  await rm(dir, { recursive: true, force: true })
}
