/**
 * Scanner de envelope `nexus-ui` parcial para renderização progressiva no stream (plano 12 §4).
 *
 * Princípio do OpenUI: "todo prefixo é uma página válida".
 * Dado o texto parcial da resposta em streaming, localiza o último fence `nexus-ui`,
 * entra na lista de `blocks` e devolve cada elemento que já fechou e é parseável.
 * O elemento em andamento não é forçado a fechar: se o seu `"type"` já chegou, ele é
 * extraído como `pendingType` para alimentar o esqueleto (Zero CLS).
 */

export interface PartialEnvelope {
  /** Elementos de `blocks` completamente fechados e parseáveis individualmente. */
  blocks: unknown[]
  /** `type` do elemento atualmente em andamento, se já recebido no prefixo. */
  pendingType: string | null
  /** `true` quando o fence de encerramento (```) foi encontrado. */
  closed: boolean
  /** `true` quando um fence `nexus-ui` de abertura foi detectado no texto. */
  found: boolean
}

const EMPTY: PartialEnvelope = { blocks: [], pendingType: null, closed: false, found: false }

const OPEN_FENCE = /(?:^|\n)[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[^\n]*\n/g
const CLOSE_FENCE = /\n[ \t]{0,3}```[ \t]*(?:\n|$)/
const BLOCKS_KEY = /"blocks"\s*:\s*\[/
const TYPE_IN_PREFIX = /"type"\s*:\s*"([a-z0-9_]{1,32})"/

export function scanPartialEnvelope(text: string): PartialEnvelope {
  if (!text) return EMPTY

  // Localiza o último fence aberto
  let openAt = -1
  for (const match of text.matchAll(OPEN_FENCE)) {
    if (match.index !== undefined) {
      openAt = match.index + match[0].length
    }
  }

  if (openAt < 0) return EMPTY

  const body = text.slice(openAt)
  const closeMatch = CLOSE_FENCE.exec('\n' + body)
  const json = closeMatch ? body.slice(0, closeMatch.index) : body
  const closed = closeMatch !== null

  const blocksKey = BLOCKS_KEY.exec(json)
  if (!blocksKey) {
    // Caso de bloco único sem o array `blocks: [`
    const singleTypeMatch = TYPE_IN_PREFIX.exec(json)
    const pendingType = singleTypeMatch ? singleTypeMatch[1] : null

    // Tenta parsear o bloco único caso ele já tenha fechado suas chaves {}
    const trimmed = json.trim()
    if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
      try {
        const parsed = JSON.parse(trimmed)
        if (parsed && typeof parsed === 'object') {
          return { blocks: [parsed], pendingType: null, closed, found: true }
        }
      } catch {
        /* ainda incompleto ou malformado */
      }
    }

    return { blocks: [], pendingType, closed, found: true }
  }

  const blocks: unknown[] = []
  let pendingType: string | null = null

  // Autômato de varredura: profundidade de {}, estado dentro de string, escape
  let depth = 0
  let inString = false
  let escaped = false
  let itemStart = -1

  const startIndex = blocksKey.index + blocksKey[0].length

  for (let i = startIndex; i < json.length; i++) {
    const ch = json[i]

    if (inString) {
      if (escaped) {
        escaped = false
      } else if (ch === '\\') {
        escaped = true
      } else if (ch === '"') {
        inString = false
      }
      continue
    }

    if (ch === '"') {
      inString = true
      continue
    }

    if (ch === '{') {
      if (depth === 0) {
        itemStart = i
      }
      depth++
      continue
    }

    if (ch === '}') {
      depth--
      if (depth === 0 && itemStart >= 0) {
        const itemStr = json.slice(itemStart, i + 1)
        try {
          const parsed = JSON.parse(itemStr)
          if (parsed && typeof parsed === 'object') {
            blocks.push(parsed)
          }
        } catch {
          // Bloco fechado mas malformado é descartado isoladamente
        }
        itemStart = -1
      }
      continue
    }

    if (ch === ']' && depth === 0) {
      // Fim do array blocks: [ ... ]
      break
    }
  }

  // Se houver um item iniciado que ainda não fechou sua profundidade
  if (itemStart >= 0) {
    const partialItem = json.slice(itemStart)
    const typeMatch = TYPE_IN_PREFIX.exec(partialItem)
    pendingType = typeMatch ? typeMatch[1] : null
  }

  return { blocks, pendingType, closed, found: true }
}
