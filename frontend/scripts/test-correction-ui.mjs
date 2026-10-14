import { build } from 'esbuild'
import { mkdtemp, rm } from 'node:fs/promises'
import { resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

// Compile only test JSX. Real React components, deterministic hooks/API fakes.
const dir = await mkdtemp(resolve('node_modules/.correction-tests-'))
try {
  const outfile = resolve(dir, 'tests.mjs')
  await build({
    entryPoints: ['scripts/tests/correction.ui.tsx'], outfile,
    bundle: true, platform: 'node', format: 'esm', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-test-renderer', 'lucide-react', 'node:*'],
    plugins: [{ name: 'deterministic-ui-hooks', setup(build) {
      build.onResolve({ filter: /useStore$|useIntelligentUi$|ChatContext$|api\/client$|useMotionAndViewport$|useResolvedTheme$|themeBridge$|^react-i18next$/ }, () => ({ path: resolve('scripts/tests/uiStubs.ts') }))
    } }],
  })
  const result = spawnSync(process.execPath, ['--test', outfile], { stdio: 'inherit' })
  process.exitCode = result.status ?? 1
} finally {
  await rm(dir, { recursive: true, force: true })
}
