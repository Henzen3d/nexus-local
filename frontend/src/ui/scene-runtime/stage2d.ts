import type { SceneTheme } from '../scene/sceneProtocol'
import type { Stage } from './stage3d'

export function mount2d(
  _title: string,
  _theme: SceneTheme,
  fail: (message: string) => void,
): Stage {
  const container = document.createElement('div')
  container.style.position = 'absolute'
  container.style.inset = '0'
  container.style.display = 'flex'
  container.style.alignItems = 'center'
  container.style.justifyContent = 'center'
  container.style.overflow = 'hidden'
  container.style.background = 'transparent'
  document.body.appendChild(container)

  const canvas = document.createElement('canvas')
  canvas.width = 800
  canvas.height = 450
  canvas.style.display = 'block'
  canvas.style.maxWidth = '100%'
  canvas.style.maxHeight = '100%'
  canvas.style.objectFit = 'contain'
  container.appendChild(canvas)

  const ctx = canvas.getContext('2d')
  if (!ctx) {
    fail('Could not acquire 2D canvas context')
    return {
      globals: { width: 800, height: 450 },
      render() {},
    }
  }

  function resize() {
    const parentW = container.clientWidth || window.innerWidth
    const parentH = container.clientHeight || window.innerHeight
    if (parentW <= 0 || parentH <= 0) return
    const scale = Math.min(parentW / 800, parentH / 450)
    canvas.style.width = `${Math.floor(800 * scale)}px`
    canvas.style.height = `${Math.floor(450 * scale)}px`
  }

  window.addEventListener('resize', resize)
  resize()

  return {
    globals: {
      ctx,
      canvas,
      width: 800,
      height: 450,
    },
    render() {
      // O código do modelo desenha diretamente no ctx durante onFrame(t, dt)
    },
  }
}
