import { useEffect, useState } from 'react'

/**
 * `prefers-reduced-motion: reduce` como estado React (spec §7: barra sem animação,
 * gráfico sem animação de entrada, cena começa pausada).
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => prefersReducedMotion())
  useEffect(() => {
    if (typeof matchMedia !== 'function') return
    const query = matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReduced(query.matches)
    query.addEventListener?.('change', onChange)
    return () => query.removeEventListener?.('change', onChange)
  }, [])
  return reduced
}

export function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

/**
 * Verdadeiro quando o elemento está a menos de uma tela de distância do viewport.
 * Vira `true` uma vez e não volta: iframes pesados (sandbox, cena) montam quando o
 * usuário se aproxima e não perdem estado depois. Ideia do `useNearScreen` do
 * AnswerUI (MIT), que descarrega cenas distantes por causa do limite de contextos
 * WebGL; aqui só adiamos a montagem.
 *
 * Sem `IntersectionObserver` (teste, navegador antigo) devolve `true` direto.
 */
export function useNearScreen(element: HTMLElement | null, margin = '100% 0px'): boolean {
  const [near, setNear] = useState<boolean>(() => typeof IntersectionObserver === 'undefined')
  useEffect(() => {
    if (near || !element || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setNear(true)
          observer.disconnect()
        }
      },
      { root: scrollParent(element), rootMargin: margin }
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [element, margin, near])
  return near
}

function scrollParent(element: HTMLElement): HTMLElement | null {
  for (let node = element.parentElement; node; node = node.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node
  }
  return null
}
