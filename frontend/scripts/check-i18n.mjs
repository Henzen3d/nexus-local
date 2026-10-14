#!/usr/bin/env node
// check-i18n.mjs — compara as chaves de `pt-BR.json` (referência) com os outros
// locales e falha se faltar chave em algum deles (F5.5.4).
//
//   node scripts/check-i18n.mjs            # todas as chaves
//   node scripts/check-i18n.mjs proactive  # só a subárvore `proactive.*`
//   node scripts/check-i18n.mjs --strict   # também falha com chaves extras / duplicadas
//
// Os JSONs têm chaves duplicadas herdadas (o último valor vence no JSON.parse);
// por padrão apenas avisamos — `--strict` transforma em erro.

import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const localesDir = join(here, '..', 'src', 'i18n', 'locales')
const REFERENCE = 'pt-BR'

const args = process.argv.slice(2)
const strict = args.includes('--strict')
const prefix = args.find((a) => !a.startsWith('--')) || ''

function flatten(obj, base = '', out = new Map()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = base ? `${base}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) flatten(v, key, out)
    else out.set(key, v)
  }
  return out
}

/** Conta chaves duplicadas no mesmo objeto (sem parser completo: varre pares "chave": por nível de indentação). */
function duplicateKeys(text) {
  const dups = []
  const stack = [new Map()]
  const lines = text.split('\n')
  for (const line of lines) {
    const m = line.match(/^(\s*)"([^"]+)"\s*:\s*(\{)?/)
    const closes = (line.match(/^\s*[}\]]/) || [])[0]
    if (closes) stack.pop()
    if (!m) continue
    const depth = m[1].length / 2
    while (stack.length > depth) stack.pop()
    while (stack.length < depth) stack.push(new Map())
    const scope = stack[stack.length - 1]
    scope.set(m[2], (scope.get(m[2]) || 0) + 1)
    if (scope.get(m[2]) === 2) dups.push(m[2])
    if (m[3]) stack.push(new Map())
  }
  return dups
}

const files = readdirSync(localesDir).filter((f) => f.endsWith('.json'))
const load = (f) => JSON.parse(readFileSync(join(localesDir, f), 'utf8'))
const refKeys = [...flatten(load(`${REFERENCE}.json`)).keys()].filter((k) => k.startsWith(prefix))

let failed = false
console.log(`i18n check — referência ${REFERENCE} (${refKeys.length} chaves${prefix ? ` em "${prefix}"` : ''})`)
for (const file of files.sort()) {
  const locale = file.replace(/\.json$/, '')
  const text = readFileSync(join(localesDir, file), 'utf8')
  const keys = new Set([...flatten(JSON.parse(text)).keys()].filter((k) => k.startsWith(prefix)))
  const missing = refKeys.filter((k) => !keys.has(k))
  const extra = [...keys].filter((k) => !refKeys.includes(k))
  const dups = prefix ? [] : duplicateKeys(text)
  const status = missing.length ? 'FALTANDO' : 'ok'
  console.log(`  ${locale.padEnd(7)} ${status}  faltando=${missing.length} extras=${extra.length} duplicadas=${dups.length}`)
  for (const k of missing.slice(0, 50)) console.log(`      - ${k}`)
  if (missing.length > 50) console.log(`      … e mais ${missing.length - 50}`)
  if (missing.length) failed = true
  if (strict && (extra.length || dups.length)) {
    failed = true
    for (const k of extra.slice(0, 20)) console.log(`      + extra: ${k}`)
    for (const k of dups.slice(0, 20)) console.log(`      ! duplicada: ${k}`)
  }
}

if (failed) {
  console.error('\ni18n check: FALHOU')
  process.exit(1)
}
console.log('\ni18n check: OK')
