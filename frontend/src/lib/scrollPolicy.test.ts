import assert from "node:assert/strict"
import test from "node:test"
import { streamScrollBehavior } from "./scrollPolicy.ts"

test("stream usa auto para não animar a cada token", () => {
  assert.equal(streamScrollBehavior(true), "auto")
})

test("lista parada usa smooth", () => {
  assert.equal(streamScrollBehavior(false), "smooth")
})
