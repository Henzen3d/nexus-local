/**
 * Scanner de envelope `nexus-ui` parcial, para o render progressivo (plano 12 §4).
 *
 * Código próprio (não é cópia); a ideia vem do princípio do OpenUI "todo prefixo é uma
 * página válida" e do `state-lines.ts` do AnswerUI (segurar o que ainda não fechou).
 *
 * O que faz: dado o texto da resposta como chegou até agora, acha o último fence
 * ```nexus-ui aberto, entra em `"blocks": [` e devolve cada elemento **completo** da lista,
 * já parseado. O elemento em andamento não é fechado à força — só o seu `"type"` é lido
 * (quando já chegou) para o esqueleto ter a altura certa.
 *
 * Garantias que os testes de propriedade devem cobrir:
 *   1. `scan(prefixo).blocks` é prefixo (em ordem e conteúdo) de `scan(textoCompleto).blocks`.
 *   2. Para um fence válido completo, `scan(texto).blocks` == `JSON.parse(fence).blocks`.
 *   3. Nenhum prefixo lança exceção.
 *
 * Complexidade O(n) no sufixo depois da abertura do fence; o chamador já usa
 * `useDeferredValue` para não rodar a cada caractere.
 */

export type PartialEnvelope = {
  /** Elementos de `blocks` fechados e parseáveis, na ordem. Cada um ainda passa pelo validador. */
  blocks: unknown[];
  /** `type` do elemento em andamento, se já apareceu; serve para o esqueleto. */
  pendingType: string | null;
  /** `true` quando o fence foi fechado (```) — a partir daí o `stream_end` manda. */
  closed: boolean;
  /** `false` quando nem há fence aberto no texto. */
  found: boolean;
};

const EMPTY: PartialEnvelope = { blocks: [], pendingType: null, closed: false, found: false };

const OPEN_FENCE = /(^|\n)```nexus-ui[^\n]*\n/g;
const CLOSE_FENCE = /\n```[ \t]*(\n|$)/;
const BLOCKS_KEY = /"blocks"\s*:\s*\[/;
const TYPE_IN_PREFIX = /"type"\s*:\s*"([a-z_]{1,24})"/;

export function scanPartialEnvelope(text: string): PartialEnvelope {
  // Último fence aberto: o modelo só deve mandar um, mas se houver dois vale o último.
  let openAt = -1;
  for (const match of text.matchAll(OPEN_FENCE)) openAt = match.index! + match[0].length;
  if (openAt < 0) return EMPTY;

  const body = text.slice(openAt);
  const closeMatch = CLOSE_FENCE.exec("\n" + body);
  const json = closeMatch ? body.slice(0, closeMatch.index) : body;
  const closed = closeMatch !== null;

  const blocksKey = BLOCKS_KEY.exec(json);
  if (!blocksKey) return { blocks: [], pendingType: null, closed, found: true };

  const blocks: unknown[] = [];
  let pendingType: string | null = null;

  // Autômato mínimo: profundidade de {} / [], dentro de string, escape.
  let depth = 0; // relativo ao interior de `blocks: [`
  let inString = false;
  let escaped = false;
  let itemStart = -1;

  for (let i = blocksKey.index + blocksKey[0].length; i < json.length; i++) {
    const ch = json[i];

    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }

    if (ch === '"') {
      inString = true;
      continue;
    }

    if (ch === "{" || ch === "[") {
      if (depth === 0) itemStart = i;
      depth++;
      continue;
    }

    if (ch === "}" || ch === "]") {
      if (depth === 0) break; // `]` que fecha `blocks`: acabou a lista
      depth--;
      if (depth === 0 && itemStart >= 0) {
        const parsed = tryParse(json.slice(itemStart, i + 1));
        if (parsed !== undefined) blocks.push(parsed);
        itemStart = -1;
      }
    }
  }

  if (itemStart >= 0) {
    const typeMatch = TYPE_IN_PREFIX.exec(json.slice(itemStart));
    pendingType = typeMatch ? typeMatch[1] : null;
  }

  return { blocks, pendingType, closed, found: true };
}

function tryParse(source: string): unknown {
  try {
    return JSON.parse(source);
  } catch {
    // Elemento fechado mas inválido (vírgula sobrando, aspas erradas): cai sozinho,
    // o resto segue — "a menor unidade que falha é descartada".
    return undefined;
  }
}
