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
    bubblesDuringTokens: number
  }
  assert.equal(data.chatWindowCommitsDuringTokens, 0)
  assert.equal(data.bubblesDuringTokens, 0)
})
