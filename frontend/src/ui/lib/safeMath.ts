/**
 * Avaliador aritmético seguro e determinístico para o ControlsCard.
 * Suporta +, -, *, /, parênteses e substituição de variáveis numéricas.
 * Estritamente sem eval() ou Function().
 */

export function evaluateSafeFormula(
  formula: string,
  variables: Record<string, number>
): number | null {
  if (!formula || typeof formula !== 'string') return null

  // Substitui as variáveis {id} pelos valores numéricos
  let resolved = formula
  for (const [key, val] of Object.entries(variables)) {
    const num = typeof val === 'number' && Number.isFinite(val) ? val : 0
    resolved = resolved.split(`{${key}}`).join(String(num))
  }

  // Remove espaços
  resolved = resolved.replace(/\s+/g, '')

  // Valida que apenas caracteres aritméticos permitidos existem
  if (!/^[0-9.+\-*/()]+$/.test(resolved)) {
    return null
  }

  try {
    let pos = 0

    function peek(): string {
      return resolved[pos] || ''
    }

    function get(): string {
      return resolved[pos++] || ''
    }

    function parseNumber(): number {
      let numStr = ''
      if (peek() === '+' || peek() === '-') {
        numStr += get()
      }
      while (/[0-9.]/.test(peek())) {
        numStr += get()
      }
      const n = parseFloat(numStr)
      if (Number.isNaN(n) || !Number.isFinite(n)) {
        throw new Error('Invalid number')
      }
      return n
    }

    function parseFactor(): number {
      if (peek() === '(') {
        get() // consome '('
        const result = parseExpression()
        if (get() !== ')') {
          throw new Error('Missing closing parenthesis')
        }
        return result
      }
      return parseNumber()
    }

    function parseTerm(): number {
      let result = parseFactor()
      while (peek() === '*' || peek() === '/') {
        const op = get()
        const next = parseFactor()
        if (op === '*') {
          result *= next
        } else {
          if (next === 0) return 0 // Prevenção de divisão por zero
          result /= next
        }
      }
      return result
    }

    function parseExpression(): number {
      let result = parseTerm()
      while (peek() === '+' || peek() === '-') {
        const op = get()
        const next = parseTerm()
        if (op === '+') {
          result += next
        } else {
          result -= next
        }
      }
      return result
    }

    const finalVal = parseExpression()
    return Number.isFinite(finalVal) ? Math.round(finalVal * 100) / 100 : null
  } catch {
    return null
  }
}
