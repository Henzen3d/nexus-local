import type { SceneValues } from '../scene/sceneProtocol'

export function createReporter(send: (values: SceneValues) => void, interval = 100) {
  let latest: SceneValues = {}
  let sent = '{}'
  let timer: ReturnType<typeof setTimeout> | undefined

  function flush() {
    timer = undefined
    const snapshot = JSON.stringify(latest)
    if (snapshot === sent) return
    sent = snapshot
    send(latest)
  }

  return (values: SceneValues) => {
    latest = { ...latest, ...values }
    timer ??= setTimeout(flush, interval)
  }
}
