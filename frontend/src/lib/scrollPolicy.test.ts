import assert from "node:assert/strict"
import test from "node:test"
import { streamScrollBehavior } from "./scrollPolicy.ts"

test("stream usa auto para não animar a cada token", () => {
  assert.equal(streamScrollBehavior(true), "auto")
})

test("lista parada usa smooth", () => {
  assert.equal(streamScrollBehavior(false), "smooth")
})

import { readFileSync } from "node:fs"

test("MessageBubble não assina o store inteiro", () => {
  const source = readFileSync(
    new URL("../components/MessageBubble.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(source.includes("} = useStore()"), false)
  assert.equal(source.includes("s.setActiveArtifact"), true)
})

test("ChatWindow usa a política de scroll", () => {
  const source = readFileSync(
    new URL("../components/ChatWindow.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(source.includes("streamScrollBehavior"), true)
})
