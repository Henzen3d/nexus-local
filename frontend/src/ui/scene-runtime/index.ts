import type { FromScene, SceneSetup, SceneTheme, SceneValues, ToScene } from '../scene/sceneProtocol'
import { SCENE_MSG } from '../scene/sceneProtocol'
import { createClock } from './clock'
import { createReporter } from './reporter'
import { mount2d } from './stage2d'
import type { Stage } from './stage3d'
import { mount3d } from './stage3d'

type FrameHandler = (t: number, dt: number) => void

const handlers: FrameHandler[] = []
const clock = createClock()
let reportFn: (values: SceneValues) => void = () => {}
let params: Record<string, unknown> = {}
let stage: Stage | undefined
let paused = false
let failed = false
let scheduled = false

function send(message: FromScene) {
  try {
    window.parent.postMessage(message, '*')
  } catch {
    // Falha silenciosa se desconectado
  }
}

function fail(error: unknown) {
  if (failed) return
  failed = true
  const msg = error instanceof Error ? error.message : String(error)
  send({
    type: SCENE_MSG.error,
    message: msg,
  })
}

function draw(dt: number) {
  if (failed) return
  try {
    for (const handler of handlers) {
      handler(clock.time, dt)
    }
    stage?.render()
  } catch (error) {
    fail(error)
  }
}

function schedule() {
  if (scheduled || paused || failed) return
  scheduled = true
  requestAnimationFrame((now) => {
    scheduled = false
    if (paused || failed) return
    draw(clock.tick(now))
    schedule()
  })
}

function receive(event: MessageEvent<ToScene>) {
  if (event.source !== window.parent) return
  const message = event.data
  if (!message || typeof message !== 'object') return

  switch (message.type) {
    case SCENE_MSG.params:
      Object.assign(params, message.values)
      if (paused) draw(0)
      break
    case SCENE_MSG.pause:
      paused = true
      clock.hold()
      break
    case SCENE_MSG.play:
      paused = false
      schedule()
      break
    case SCENE_MSG.theme:
      stage?.retheme?.(message.theme)
      if (paused) draw(0)
      break
  }
}

export function setup(
  config: SceneSetup,
) {
  window.addEventListener('error', (event) => fail(event.error ?? event.message))
  window.addEventListener('unhandledrejection', (event) => fail(event.reason))

  params = { ...config.params }
  paused = config.paused
  const reporter = createReporter((values) => send({ type: SCENE_MSG.report, values }))
  reportFn = reporter

  const mounts = { '3d': mount3d, '2d': mount2d }
  const mountMode = mounts[config.mode] ? mounts[config.mode] : mount3d
  stage = mountMode(config.title, config.theme, fail)

  const onFrame = (handler: FrameHandler) => {
    handlers.length = 0
    handlers.push(handler)
  }

  // Remove timers perigosos do escopo global da cena antes do código do modelo rodar
  const cleanGlobals = {
    params,
    theme: config.theme,
    onFrame,
    report: reportFn,
  }

  Object.assign(globalThis, stage.globals, cleanGlobals)
}

export function start(ownScene: unknown, ownCamera: unknown) {
  if (failed) return
  stage?.adopt?.(ownScene, ownCamera)
  window.addEventListener('message', receive)
  window.addEventListener('resize', () => {
    if (paused) draw(0)
  })

  send({ type: SCENE_MSG.ready })
  if (paused) {
    draw(0)
  } else {
    schedule()
  }
}

const NexusScene = {
  setup,
  start,
}

// Expõe NexusScene no escopo global para chamada a partir do srcdoc da cena
;(globalThis as any).NexusScene = NexusScene

export default NexusScene
