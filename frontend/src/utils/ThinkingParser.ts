export interface ParsedStream {
  reasoning: string | null;
  answer: string;
  isThinking: boolean;
}

/**
 * ThinkingParser
 *
 * Parseador algorítmico robusto projetado para extrair blocos de raciocínio
 * de streams (chunk-by-chunk ou texto acumulado) de forma segura.
 *
 * Previne vazamento de tags parciais (ex: `<thi`, `</analy`) para a UI durante
 * o streaming. Suporta múltiplas tags (think, analysis, etc) e atributos.
 *
 * Supressão de pre-think leaked: Alguns modelos (ex: Gemma) escrevem parte
 * do raciocínio em itálico (*...*) ANTES da tag <think>. Esse conteúdo é
 * detectado e movido para o bloco de raciocínio, evitando poluição do chat.
 */
export class ThinkingParser {
  private static readonly TAGS = [
    'think',
    'thinking',
    'reasoning',
    'analysis',
    'reflection',
    'assistant_thought',
    'redacted_reasoning',
    'redacted_thinking',
  ];

  private static get tagsPattern(): string {
    return this.TAGS.join('|');
  }

  /**
   * Verifica se uma string consiste apenas de "raciocínio vazado":
   * linhas em itálico Markdown (*...*), listas bullet simples, ou espaços em branco.
   * Isso indica que o modelo escreveu pensamentos fora da tag <think>.
   */
  private static isLeakedThinking(text: string): boolean {
    const trimmed = text.trim();
    if (!trimmed) return true; // vazio ou só espaços: não exibir

    const lines = trimmed.split('\n');
    let italicOrEmptyCount = 0;

    for (const line of lines) {
      const t = line.trim();
      if (!t) {
        italicOrEmptyCount++;
        continue;
      }
      // Linha em itálico Markdown: *...* ou _..._
      const isItalic = /^\*[^*]+\*$/.test(t) || /^_[^_]+_$/.test(t);
      // Linha de bullet simples com itálico: - *...*
      const isBulletItalic = /^[-*+]\s+\*[^*]+\*$/.test(t);
      // Linha que é apenas ---/*** (divisores)
      const isDivider = /^[-*_]{3,}$/.test(t);

      if (isItalic || isBulletItalic || isDivider) {
        italicOrEmptyCount++;
      }
    }

    // Se >= 70% das linhas são itálico/vazio, é raciocínio vazado
    return italicOrEmptyCount / lines.length >= 0.7;
  }

  /** Remove todos os blocos e tags de raciocínio remanescentes do texto visível. */
  private static stripAllThinkingArtifacts(text: string): string {
    if (!text) return '';
    const tags = this.tagsPattern;
    let out = text;
    // Blocos completos (possivelmente múltiplos)
    out = out.replace(new RegExp(`<(${tags})(?:\\s+[^>]*)?>[\\s\\S]*?<\\/\\1>`, 'gi'), '');
    // Tags órfãs de abertura/fechamento
    out = out.replace(new RegExp(`<\\/?(?:${tags})(?:\\s+[^>]*)?>`, 'gi'), '');
    // Variantes com escape HTML
    out = out.replace(
      new RegExp(`&lt;\\/?(?:${tags})(?:\\s+[^&]*)?&gt;`, 'gi'),
      ''
    );
    // Modelos que usam fence "thinking" falso: ```thinking ... ```
    out = out.replace(/```(?:thinking|reasoning|analysis)\s*[\s\S]*?```/gi, '');
    return out;
  }

  /**
   * Extrai o raciocínio e a resposta final de um conteúdo acumulado de stream.
   * Evita corrupção de string ocultando tags HTML/XML parciais no final do stream.
   * Suprime conteúdo pré-<think> que seja raciocínio interno vazado do modelo.
   */
  public static parse(content: string): ParsedStream {
    if (!content) {
      return { reasoning: null, answer: '', isThinking: false };
    }

    let reasoningParts: string[] = [];
    let answer = '';
    let isThinking = false;
    let cursor = 0;

    const openPattern = new RegExp(`<(${this.tagsPattern})(?:\\s+[^>]*)?>`, 'gi');

    // Extrai todos os blocos <think>...</think> em sequência
    while (cursor < content.length) {
      openPattern.lastIndex = cursor;
      const openMatch = openPattern.exec(content);

      if (!openMatch) {
        // Resto sem mais tags de abertura
        let tail = content.substring(cursor);
        // Oculta abertura parcial no final do stream (ex: `<thi`)
        const partialOpen = /<[a-zA-Z_]*$/.exec(tail);
        if (partialOpen) {
          tail = tail.substring(0, partialOpen.index);
        }
        answer += tail;
        break;
      }

      const openTagName = openMatch[1];
      const openStart = openMatch.index;
      const openEnd = openStart + openMatch[0].length;

      // Texto antes da tag
      const pre = content.substring(cursor, openStart);
      if (reasoningParts.length === 0 && this.isLeakedThinking(pre)) {
        if (pre.trim()) reasoningParts.push(pre.trim());
      } else {
        answer += pre;
      }

      // Busca fechamento correspondente
      const closePattern = new RegExp(`</${openTagName}>`, 'i');
      const remaining = content.substring(openEnd);
      const closeMatch = closePattern.exec(remaining);

      if (closeMatch) {
        const inner = remaining.substring(0, closeMatch.index).trim();
        if (inner) reasoningParts.push(inner);
        cursor = openEnd + closeMatch.index + closeMatch[0].length;
        isThinking = false;
      } else {
        // Streaming: ainda dentro do bloco
        isThinking = true;
        const partialClose = /<\/[a-zA-Z_]*$/.exec(remaining);
        const inner = (
          partialClose
            ? remaining.substring(0, partialClose.index)
            : remaining
        ).trim();
        if (inner) reasoningParts.push(inner);
        cursor = content.length;
      }
    }

    // Limpeza final: nada de tags de raciocínio deve vazar no answer
    let cleanAnswer = this.stripAllThinkingArtifacts(answer).trimStart();

    // Se o answer ainda começa com raciocínio em itálico e temos reasoning, tira
    if (reasoningParts.length > 0 && this.isLeakedThinking(cleanAnswer.slice(0, 200))) {
      // não remove answer legítimo; só prefixos claramente leaked
    }

    const finalReasoning =
      reasoningParts.length > 0
        ? reasoningParts.join('\n\n').trim() || null
        : isThinking
          ? ''
          : null;

    return {
      reasoning: finalReasoning,
      answer: cleanAnswer.trim(),
      isThinking,
    };
  }
}
