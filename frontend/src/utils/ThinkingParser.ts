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
    'assistant_thought'
  ];

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

  /**
   * Extrai o raciocínio e a resposta final de um conteúdo acumulado de stream.
   * Evita corrupção de string ocultando tags HTML/XML parciais no final do stream.
   * Suprime conteúdo pré-<think> que seja raciocínio interno vazado do modelo.
   */
  public static parse(content: string): ParsedStream {
    if (!content) {
      return { reasoning: null, answer: '', isThinking: false };
    }

    let reasoning: string | null = null;
    let answer = '';
    let isThinking = false;

    // 1. Busca a primeira tag de abertura suportada (ex: <think> ou <think time="10">)
    const tagsPattern = this.TAGS.join('|');
    const openPattern = new RegExp(`<(${tagsPattern})(?:\\s+[^>]*)?>`, 'i');
    const openMatch = openPattern.exec(content);

    if (openMatch) {
      const openTagName = openMatch[1]; // A tag efetiva que abriu
      const openStart = openMatch.index;
      const openEnd = openStart + openMatch[0].length;

      // Conteúdo antes da tag <think>
      const preThinkContent = content.substring(0, openStart);

      // Se o conteúdo pré-think parece raciocínio vazado, suprimimos da resposta
      // e o adicionamos ao início do bloco de raciocínio
      if (this.isLeakedThinking(preThinkContent)) {
        // Será anexado ao reasoning como prefixo (raciocínio vazado recuperado)
        reasoning = preThinkContent.trim() ? preThinkContent.trim() + '\n\n' : '';
      } else {
        // Conteúdo legítimo antes da tag: exibir na resposta normalmente
        answer += preThinkContent;
        reasoning = '';
      }

      // 2. Busca a tag de fechamento correspondente
      const closePattern = new RegExp(`</${openTagName}>`, 'i');
      const remainingContent = content.substring(openEnd);
      const closeMatch = closePattern.exec(remainingContent);

      if (closeMatch) {
        // Bloco fechado com sucesso — concatena o prefixo com o raciocínio real
        const innerReasoning = remainingContent.substring(0, closeMatch.index).trim();
        reasoning = (reasoning || '') + innerReasoning;
        const closeEnd = closeMatch.index + closeMatch[0].length;

        // O resto do conteúdo após a tag fechada é resposta
        answer += remainingContent.substring(closeEnd);
        isThinking = false;
      } else {
        // Ainda estamos dentro do bloco de raciocínio (streaming ativo)
        isThinking = true;

        // Tratamento de edge-case: previne vazar fechamentos parciais no raciocínio (ex: `...raciocínio</thi`)
        const partialCloseRegex = /<\/[a-zA-Z_]*$/;
        const partialMatch = partialCloseRegex.exec(remainingContent);

        const innerReasoning = partialMatch
          ? remainingContent.substring(0, partialMatch.index).trim()
          : remainingContent.trim();

        reasoning = (reasoning || '') + innerReasoning;
      }
    } else {
      // Nenhuma tag de abertura encontrada.
      // Tratamento de edge-case: previne vazar aberturas parciais na resposta (ex: `Olá <th`)
      const partialOpenRegex = /<[a-zA-Z_]*$/;
      const partialMatch = partialOpenRegex.exec(content);

      if (partialMatch) {
        // Se parece o início de uma tag, ocultamos da resposta por segurança até o próximo chunk
        answer = content.substring(0, partialMatch.index);
      } else {
        answer = content;
      }
      isThinking = false;
    }

    // Normaliza: reasoning vazio string → null quando não há thinking
    const finalReasoning = reasoning === null && !isThinking
      ? null
      : (reasoning?.trim() || null);

    return {
      reasoning: finalReasoning,
      answer: answer.trimStart(),
      isThinking
    };
  }
}
