import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DRenderer, CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import type { SceneTheme } from '../scene/sceneProtocol'

export type Stage = {
  globals: Record<string, unknown>
  render(): void
  adopt?(scene: unknown, camera: unknown): void
  retheme?(theme: SceneTheme): void
}

export function mount3d(
  _title: string,
  theme: SceneTheme,
  fail: (message: string) => void,
): Stage {
  const container = document.createElement('div')
  container.style.position = 'absolute'
  container.style.inset = '0'
  container.style.overflow = 'hidden'
  document.body.appendChild(container)

  let width = container.clientWidth || window.innerWidth || 800
  let height = container.clientHeight || window.innerHeight || 450

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(50, width / height, 0.1, 1000)
  camera.position.set(4, 3, 6)
  camera.lookAt(0, 0, 0)

  // Iluminação padrão de estúdio
  const ambientLight = new THREE.AmbientLight(0xffffff, 0.8)
  scene.add(ambientLight)
  const dirLight = new THREE.DirectionalLight(0xffffff, 1.0)
  dirLight.position.set(5, 10, 7)
  scene.add(dirLight)

  // WebGL Renderer com suporte a alpha
  let renderer: THREE.WebGLRenderer
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  } catch {
    fail('WebGL context creation failed')
    return {
      globals: { THREE, scene, camera },
      render() {},
    }
  }

  renderer.setSize(width, height)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  container.appendChild(renderer.domElement)

  // Captura perda de contexto WebGL
  renderer.domElement.addEventListener('webglcontextlost', (e) => {
    e.preventDefault()
    fail('webglcontextlost')
  })

  // CSS2DRenderer para rótulos em texto acessíveis
  const labelRenderer = new CSS2DRenderer()
  labelRenderer.setSize(width, height)
  labelRenderer.domElement.style.position = 'absolute'
  labelRenderer.domElement.style.top = '0'
  labelRenderer.domElement.style.pointerEvents = 'none'
  container.appendChild(labelRenderer.domElement)

  // OrbitControls com amortecimento
  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.05

  // Rótulos 3D (label helper)
  const labels: HTMLElement[] = []
  function label(object: THREE.Object3D, text: string) {
    const div = document.createElement('div')
    div.className = 'nexus-scene-label'
    div.textContent = String(text || '').slice(0, 40)
    div.style.color = theme.text || '#ffffff'
    div.style.fontFamily = 'system-ui, -apple-system, sans-serif'
    div.style.fontSize = '12px'
    div.style.fontWeight = '500'
    div.style.padding = '2px 6px'
    div.style.borderRadius = '4px'
    div.style.backgroundColor = theme.dark ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.8)'
    div.style.border = `1px solid ${theme.accent || 'rgba(128,128,128,0.4)'}`
    div.style.pointerEvents = 'none'
    labels.push(div)

    const c2dObj = new CSS2DObject(div)
    c2dObj.position.set(0, 0, 0)
    object.add(c2dObj)
    return c2dObj
  }

  function resize() {
    width = container.clientWidth || window.innerWidth
    height = container.clientHeight || window.innerHeight
    if (width <= 0 || height <= 0) return
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height)
    labelRenderer.setSize(width, height)
  }

  window.addEventListener('resize', resize)

  let activeScene = scene
  let activeCamera = camera

  return {
    globals: {
      THREE,
      scene,
      camera,
      controls,
      label,
    },
    render() {
      controls.update()
      renderer.render(activeScene, activeCamera)
      labelRenderer.render(activeScene, activeCamera)
    },
    adopt(ownScene: unknown, ownCamera: unknown) {
      if (ownScene instanceof THREE.Scene) activeScene = ownScene
      if (ownCamera instanceof THREE.PerspectiveCamera || ownCamera instanceof THREE.OrthographicCamera) {
        activeCamera = ownCamera as THREE.PerspectiveCamera
      }
    },
    retheme(newTheme: SceneTheme) {
      for (const el of labels) {
        el.style.color = newTheme.text
        el.style.backgroundColor = newTheme.dark ? 'rgba(0,0,0,0.6)' : 'rgba(255,255,255,0.8)'
        el.style.borderColor = newTheme.accent
      }
    },
  }
}
