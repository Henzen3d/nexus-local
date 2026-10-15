/**
 * Avaliador aritmético e validador de expressões seguro e determinístico para o Intelligent UI.
 * Espelha rigorosamente as regras de backend/ui_blocks/expr.py.
 * Suporta +, -, *, /, parênteses, variáveis {id} e funções matemáticas seguras.
 * Estritamente sem eval() ou Function().
 */

export const MAX_EXPR_LENGTH = 160
export const MAX_EXPR_TOKENS = 40

export const ALLOWED_FUNCTIONS: Record<string, number> = {
  round: 2,
  pow: 2,
  abs: 1,
  floor: 1,
  ceil: 1,
  sqrt: 1,
  min: -1, // 1 ou mais
  max: -1, // 1 ou mais
}

const IDENTIFIER_REGEX = /^[a-zA-Z0-9_]{1,32}$/

export function isExpression(val: unknown): val is string {
  return typeof val === 'string' && val.trim().startsWith('=') && val.trim().length > 1
}

interface Token {
  kind: string
  value: string | number
}

export function tokenizeExpression(expr: string): { tokens: Token[] | null; error: string | null } {
  let text = expr.trim()
  if (text.startsWith('=')) {
    text = text.slice(1).trim()
  }

  if (!text) {
    return { tokens: null, error: 'empty_expression' }
  }

  if (expr.length > MAX_EXPR_LENGTH) {
    return { tokens: null, error: 'limit_exceeded' }
  }

  const tokens: Token[] = []
  let i = 0
  const n = text.length

  while (i < n) {
    const c = text[i]

    if (/\s/.test(c)) {
      i++
      continue
    }

    if ('+-*/(),'.includes(c)) {
      tokens.push({ kind: c, value: c })
      i++
    } else if (c === '^') {
      return { tokens: null, error: 'invalid_operator' }
    } else if (c === '{') {
      const endBrace = text.indexOf('}', i + 1)
      if (endBrace === -1) {
        return { tokens: null, error: 'invalid_identifier' }
      }
      const varName = text.slice(i + 1, endBrace).trim()
      if (!IDENTIFIER_REGEX.test(varName)) {
        return { tokens: null, error: 'invalid_identifier' }
      }
      tokens.push({ kind: 'VAR', value: varName })
      i = endBrace + 1
    } else if (/[0-9]/.test(c) || (c === '.' && i + 1 < n && /[0-9]/.test(text[i + 1]))) {
      const start = i
      while (i < n && (/[0-9]/.test(text[i]) || text[i] === '.')) {
        i++
      }
      const numStr = text.slice(start, i)
      const val = parseFloat(numStr)
      if (Number.isNaN(val)) {
        return { tokens: null, error: 'syntax_error' }
      }
      tokens.push({ kind: 'NUMBER', value: val })
    } else if (/[a-zA-Z_]/.test(c)) {
      const start = i
      while (i < n && /[a-zA-Z0-9_]/.test(text[i])) {
        i++
      }
      const name = text.slice(start, i).toLowerCase()
      if (!(name in ALLOWED_FUNCTIONS)) {
        return { tokens: null, error: 'unknown_function' }
      }
      tokens.push({ kind: 'FUNC', value: name })
    } else {
      return { tokens: null, error: 'syntax_error' }
    }

    if (tokens.length > MAX_EXPR_TOKENS) {
      return { tokens: null, error: 'limit_exceeded' }
    }
  }

  return { tokens, error: null }
}

class ExprParser {
  private tokens: Token[]
  private pos = 0
  public variables: string[] = []

  constructor(tokens: Token[]) {
    this.tokens = tokens
  }

  private peek(): Token | undefined {
    return this.tokens[this.pos]
  }

  private advance(): Token | undefined {
    return this.tokens[this.pos++]
  }

  public parse(): string | null {
    const err = this.parseExpr()
    if (err) return err
    if (this.pos < this.tokens.length) {
      const tok = this.peek()
      if (tok && tok.kind === ')') {
        return 'unbalanced_parentheses'
      }
      return 'syntax_error'
    }
    return null
  }

  private parseExpr(): string | null {
    let err = this.parseTerm()
    if (err) return err
    while (this.peek() && (this.peek()!.kind === '+' || this.peek()!.kind === '-')) {
      this.advance()
      err = this.parseTerm()
      if (err) return err
    }
    return null
  }

  private parseTerm(): string | null {
    let err = this.parseFactor()
    if (err) return err
    while (this.peek() && (this.peek()!.kind === '*' || this.peek()!.kind === '/')) {
      this.advance()
      err = this.parseFactor()
      if (err) return err
    }
    return null
  }

  private parseFactor(): string | null {
    const tok = this.peek()
    if (tok && (tok.kind === '+' || tok.kind === '-')) {
      this.advance()
    }
    return this.parsePrimary()
  }

  private parsePrimary(): string | null {
    const tok = this.peek()
    if (!tok) return 'syntax_error'

    if (tok.kind === 'NUMBER') {
      this.advance()
      return null
    }

    if (tok.kind === 'VAR') {
      this.variables.push(String(tok.value))
      this.advance()
      return null
    }

    if (tok.kind === '(') {
      this.advance()
      const err = this.parseExpr()
      if (err) return err
      const closeTok = this.peek()
      if (!closeTok || closeTok.kind !== ')') {
        return 'unbalanced_parentheses'
      }
      this.advance()
      return null
    }

    if (tok.kind === 'FUNC') {
      const funcName = String(tok.value)
      this.advance()
      if (!this.peek() || this.peek()!.kind !== '(') {
        return 'syntax_error'
      }
      this.advance() // '('

      let argCount = 0
      if (this.peek() && this.peek()!.kind !== ')') {
        const err = this.parseExpr()
        if (err) return err
        argCount++
        while (this.peek() && this.peek()!.kind === ',') {
          this.advance()
          const errNext = this.parseExpr()
          if (errNext) return errNext
          argCount++
        }
      }

      if (!this.peek() || this.peek()!.kind !== ')') {
        return 'unbalanced_parentheses'
      }
      this.advance() // ')'

      const expected = ALLOWED_FUNCTIONS[funcName] ?? 1
      if (expected === -1) {
        if (argCount < 1) return 'invalid_arity'
      } else if (argCount !== expected) {
        return 'invalid_arity'
      }

      return null
    }

    return 'syntax_error'
  }
}

export function validateExpression(
  expr: string,
  knownIds?: Set<string>
): { valid: boolean; error?: string; variables: string[] } {
  if (typeof expr !== 'string' || !expr.trim()) {
    return { valid: false, error: 'empty_expression', variables: [] }
  }

  const text = expr.trim()
  if (!text.startsWith('=')) {
    return { valid: false, error: 'invalid_expression', variables: [] }
  }

  const { tokens, error: tokError } = tokenizeExpression(text)
  if (tokError || !tokens) {
    return { valid: false, error: tokError || 'syntax_error', variables: [] }
  }

  const parser = new ExprParser(tokens)
  const syntaxErr = parser.parse()
  if (syntaxErr) {
    return { valid: false, error: syntaxErr, variables: [] }
  }

  const uniqueVars = Array.from(new Set(parser.variables))
  if (knownIds) {
    for (const v of uniqueVars) {
      if (!knownIds.has(v)) {
        return { valid: false, error: 'unknown_identifier', variables: uniqueVars }
      }
    }
  }

  return { valid: true, variables: uniqueVars }
}

export function extractExpressionVariables(expr: string): string[] {
  const res = validateExpression(expr)
  return res.variables
}

export function checkDependencyCycles(
  computeds: Array<{ id: string; formula: string }>,
  fieldIds: Set<string>
): { valid: boolean; error?: string; order: string[] } {
  if (!Array.isArray(computeds)) {
    return { valid: false, error: 'invalid_computed', order: [] }
  }

  const allKnown = new Set(fieldIds)
  const computedMap = new Map<string, string[]>()
  const computedIds: string[] = []

  for (const comp of computeds) {
    if (!comp || typeof comp !== 'object') {
      return { valid: false, error: 'invalid_computed', order: [] }
    }
    const cId = comp.id || 'resultado'
    if (!IDENTIFIER_REGEX.test(cId)) {
      return { valid: false, error: 'invalid_identifier', order: [] }
    }
    if (computedMap.has(cId) || fieldIds.has(cId)) {
      return { valid: false, error: 'duplicate_id', order: [] }
    }

    const formula = comp.formula
    if (typeof formula !== 'string') {
      return { valid: false, error: 'invalid_expression', order: [] }
    }

    const testExpr = formula.trim().startsWith('=') ? formula : `=${formula}`
    const { valid, error, variables } = validateExpression(testExpr)
    if (!valid) {
      return { valid: false, error: error || 'invalid_expression', order: [] }
    }

    computedMap.set(cId, variables)
    computedIds.push(cId)
    allKnown.add(cId)
  }

  for (const [cId, deps] of computedMap.entries()) {
    for (const d of deps) {
      if (!allKnown.has(d)) {
        return { valid: false, error: 'unknown_identifier', order: [] }
      }
    }
  }

  const WHITE = 0,
    GRAY = 1,
    BLACK = 2
  const state = new Map<string, number>()
  for (const id of computedIds) {
    state.set(id, WHITE)
  }
  const order: string[] = []

  function dfs(u: string): boolean {
    state.set(u, GRAY)
    const deps = computedMap.get(u) || []
    for (const v of deps) {
      if (state.has(v)) {
        if (state.get(v) === GRAY) return true
        if (state.get(v) === WHITE) {
          if (dfs(v)) return true
        }
      }
    }
    state.set(u, BLACK)
    order.push(u)
    return false
  }

  for (const id of computedIds) {
    if (state.get(id) === WHITE) {
      if (dfs(id)) {
        return { valid: false, error: 'cycle_detected', order: [] }
      }
    }
  }

  return { valid: true, order }
}

/**
 * Avalia a expressão com o conjunto de variáveis numéricas.
 * Retorna o resultado numérico ou null se houver erro aritmético.
 */
export function evaluateExpression(
  expr: string,
  variables: Record<string, number | string | undefined>
): number | null {
  const { valid, error } = validateExpression(expr)
  if (!valid || error) return null

  const { tokens } = tokenizeExpression(expr)
  if (!tokens) return null

  let pos = 0

  function peek(): Token | undefined {
    return tokens![pos]
  }

  function advance(): Token | undefined {
    return tokens![pos++]
  }

  function evalExpr(): number {
    let result = evalTerm()
    while (peek() && (peek()!.kind === '+' || peek()!.kind === '-')) {
      const op = advance()!.kind
      const next = evalTerm()
      if (op === '+') {
        result += next
      } else {
        result -= next
      }
    }
    return result
  }

  function evalTerm(): number {
    let result = evalFactor()
    while (peek() && (peek()!.kind === '*' || peek()!.kind === '/')) {
      const op = advance()!.kind
      const next = evalFactor()
      if (op === '*') {
        result *= next
      } else {
        if (next === 0 || !Number.isFinite(next)) {
          result = 0 // Prevenção de divisão por zero
        } else {
          result /= next
        }
      }
    }
    return result
  }

  function evalFactor(): number {
    const tok = peek()
    if (tok && (tok.kind === '+' || tok.kind === '-')) {
      const sign = advance()!.kind === '-' ? -1 : 1
      return sign * evalPrimary()
    }
    return evalPrimary()
  }

  function evalPrimary(): number {
    const tok = advance()
    if (!tok) throw new Error('Unexpected EOF')

    if (tok.kind === 'NUMBER') {
      return Number(tok.value)
    }

    if (tok.kind === 'VAR') {
      const raw = variables[String(tok.value)]
      const n = typeof raw === 'number' ? raw : parseFloat(String(raw ?? ''))
      return Number.isFinite(n) ? n : 0
    }

    if (tok.kind === '(') {
      const val = evalExpr()
      advance() // ')'
      return val
    }

    if (tok.kind === 'FUNC') {
      const name = String(tok.value)
      advance() // '('
      const args: number[] = []
      if (peek() && peek()!.kind !== ')') {
        args.push(evalExpr())
        while (peek() && peek()!.kind === ',') {
          advance()
          args.push(evalExpr())
        }
      }
      advance() // ')'

      switch (name) {
        case 'round': {
          const factor = Math.pow(10, Math.max(0, Math.min(6, Math.floor(args[1] ?? 0))))
          return Math.round((args[0] ?? 0) * factor) / factor
        }
        case 'pow':
          return Math.pow(args[0] ?? 0, args[1] ?? 1)
        case 'abs':
          return Math.abs(args[0] ?? 0)
        case 'floor':
          return Math.floor(args[0] ?? 0)
        case 'ceil':
          return Math.ceil(args[0] ?? 0)
        case 'sqrt':
          return Math.sqrt(Math.max(0, args[0] ?? 0))
        case 'min':
          return args.length > 0 ? Math.min(...args) : 0
        case 'max':
          return args.length > 0 ? Math.max(...args) : 0
        default:
          return 0
      }
    }

    return 0
  }

  try {
    const res = evalExpr()
    return Number.isFinite(res) ? Math.round(res * 1000000) / 1000000 : null
  } catch {
    return null
  }
}

/**
 * Função de retrocompatibilidade para o ControlsCard antigo.
 */
export function evaluateSafeFormula(
  formula: string,
  variables: Record<string, number>
): number | null {
  if (!formula || typeof formula !== 'string') return null
  const testExpr = formula.trim().startsWith('=') ? formula : `=${formula}`
  const evaluated = evaluateExpression(testExpr, variables)
  return evaluated !== null && Number.isFinite(evaluated) ? Math.round(evaluated * 100) / 100 : null
}
