import assert from "node:assert/strict"
import test from "node:test"
import { streamScrollBehavior } from "./scrollPolicy.ts"

test("stream usa auto para não animar a cada token", () => {
  assert.equal(streamScrollBehavior(true), "auto")
})

test("lista parada usa smooth", () => {
  assert.equal(streamScrollBehavior(false), "smooth")
})

import { readFileSync, readdirSync } from "node:fs"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"
import { spawnSync } from "node:child_process"

test("MessageBubble não assina o store inteiro", () => {
  const source = readFileSync(
    new URL("../components/MessageBubble.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(source.includes("} = useStore()"), false)
  assert.equal(source.includes("s.setActiveArtifact"), true)
})

test("ChatWindow não assina streamingContent e o scroll do stream não é smooth", () => {
  const chat = readFileSync(
    new URL("../components/ChatWindow.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(chat.includes("streamingContent"), false)

  const srcRoot = fileURLToPath(new URL("../", import.meta.url))
  const files = walkTs(srcRoot)
  const importers = files.filter((file) => {
    const source = readFileSync(file, "utf8")
    return source.split("\n").some((line) => line.includes("import") && line.includes("streamScrollBehavior"))
  })
  assert.ok(importers.length > 0)
  for (const file of importers) {
    const source = readFileSync(file, "utf8")
    assert.equal(
      source.includes("streamScrollBehavior("),
      true,
      `${file} importa streamScrollBehavior e não chama`,
    )
  }

  const streamFile = files.find((file) => {
    if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) return false
    return readFileSync(file, "utf8").includes("streamScrollBehavior(true)")
  })
  assert.ok(streamFile, "o scroll do stream tem de chamar streamScrollBehavior(true)")
  const streamSource = readFileSync(streamFile!, "utf8")
  assert.equal(streamSource.includes("behavior: 'smooth'"), false)
  assert.equal(streamSource.includes('behavior: "smooth"'), false)
})

test("efeito do stream lê a distância ao fundo (180) antes de scrollIntoView", () => {
  const srcRoot = fileURLToPath(new URL("../", import.meta.url))
  const streamFile = walkTs(srcRoot).find((file) => {
    if (file.endsWith(".test.ts") || file.endsWith(".test.tsx")) return false
    return readFileSync(file, "utf8").includes("streamScrollBehavior(true)")
  })
  assert.ok(streamFile, "o scroll do stream tem de chamar streamScrollBehavior(true)")
  const source = readFileSync(streamFile!, "utf8")
  const scrollAt = source.indexOf("scrollIntoView")
  assert.ok(scrollAt >= 0, `${streamFile} chama streamScrollBehavior(true) e não chama scrollIntoView`)
  const effectAt = source.lastIndexOf("useEffect", scrollAt)
  assert.ok(effectAt >= 0, "scrollIntoView fora de useEffect")
  const before = source.slice(effectAt, scrollAt)
  assert.match(before, /\b180\b/, "scrollIntoView roda sem ler 180 antes")
  const distAt = before.search(/scrollHeight\s*-\s*[\w.]+\.scrollTop\s*-\s*[\w.]+\.clientHeight/)
  assert.notEqual(distAt, -1, "scrollIntoView roda sem ler a distância ao fundo")
  const afterDist = before.slice(distAt)
  assert.match(
    afterDist,
    /\bif\s*\([^)]*\bisNearBottom\b/,
    "scrollIntoView roda sem a guarda de 180px",
  )
})

function walkTs(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name === "dist") continue
    const path = join(dir, entry.name)
    if (entry.isDirectory()) out.push(...walkTs(path))
    else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) out.push(path)
  }
  return out
}

test("20 tokens não aumentam commits do ChatWindow nem renders das bolhas antigas", () => {
  const frontend = dirname(fileURLToPath(new URL("../", import.meta.url)))
  const result = spawnSync(process.execPath, ["scripts/run-streaming-paint-probe.mjs"], {
    cwd: frontend,
    encoding: "utf8",
    timeout: 300000,
  })
  assert.equal(result.status, 0, result.stderr)
  const line = result.stdout.trim().split("\n").find((row) => row.startsWith("{"))
  assert.ok(line, result.stdout)
  const data = JSON.parse(line!) as {
    commitsDuringTokens: number
    chatWindowCommitsDuringTokens: number
    chatWindowRendersDuringTokens: number
    chatWindowCommitsAfterMount: number
    bubblesAfterMount: number
    bubblesDuringTokens: number
  }
  assert.equal(data.bubblesAfterMount, 50)
  assert.equal(data.bubblesDuringTokens, 0)
  assert.equal(data.chatWindowRendersDuringTokens, 0)
  assert.ok(data.chatWindowCommitsAfterMount >= 1)
  assert.equal(data.chatWindowCommitsDuringTokens, 0)
})
