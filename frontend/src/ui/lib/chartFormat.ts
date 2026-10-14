/**
 * Funções puras usadas pelo ChartCard (e por outros cartões que mostram número).
 * Sem React e sem DOM, para rodar nos testes de node (`npm test`).
 *
 * As regras vêm da leitura do OpenUI (Thesys, MIT) descrita em
 * melhorias/intelligent-ui/10-referencias-answerui-openui-openwebui.md §3.3:
 * paleta distribuída a partir do meio da rampa, ticks por altura, domínio Y
 * ancorado em zero. Reimplementadas aqui, não copiadas.
 */

/** Espaço vertical mínimo entre ticks do eixo Y, em px. */
export const MIN_TICK_SPACING = 40

/** Altura padrão da área de desenho dos gráficos nativos. */
export const CHART_HEIGHT = 220

/**
 * Rampa de cores dos gráficos, só com tokens do Multi+ (spec §7: "sem cor nova").
 * `color-mix` gera tons intermediários a partir dos mesmos tokens para 5+ séries.
 */
export const CHART_RAMP: readonly string[] = [
  'var(--primary, #cc785c)',
  'var(--cyan, #5db8a6)',
  'var(--warning, #d4a017)',
  'var(--success, #5db872)',
  'color-mix(in srgb, var(--primary, #cc785c) 55%, var(--ink, #f5f5f5))',
  'color-mix(in srgb, var(--cyan, #5db8a6) 55%, var(--ink, #f5f5f5))',
]

/**
 * Escolhe `count` cores da rampa partindo do meio para fora, para que 1 série use a
 * cor principal e 2 séries fiquem com cores vizinhas e distintas. Com mais séries do
 * que cores, a rampa repete (módulo positivo).
 */
export function distributeColors(ramp: readonly string[], count: number): string[] {
  const n = ramp.length
  if (n === 0 || count <= 0) return []
  const mid = Math.floor(n / 2)
  const wrap = (index: number) => ramp[((index % n) + n) % n]
  if (count === 1) return [ramp[mid]]
  if (count === 2) return [ramp[Math.max(mid - 1, 0)], ramp[Math.min(mid + 1, n - 1)]]
  const offset = Math.floor((count - 1) / 2)
  const out: string[] = []
  for (let i = 0; i < count; i++) out.push(wrap(mid + (i - offset)))
  return out
}

/** Cores das séries do Nexus: a primeira série fica sempre com `--primary`. */
export function seriesColors(count: number): string[] {
  if (count <= 0) return []
  if (count === 1) return [CHART_RAMP[0]]
  // Para 2+ séries, usa a rampa na ordem (primary, cyan, warning, …): tons bem separados.
  const out: string[] = []
  for (let i = 0; i < count; i++) out.push(CHART_RAMP[i % CHART_RAMP.length])
  return out
}

/** Quantos ticks cabem no eixo Y para a altura dada (mínimo 2, um a cada 40 px). */
export function tickCountFor(height: number, spacing = MIN_TICK_SPACING): number {
  if (!Number.isFinite(height) || height <= 0) return 2
  return Math.max(2, Math.floor(height / spacing))
}

/**
 * Domínio Y sempre passando por zero: `[min(0, menor), max(0, maior)]`.
 * Com `stacked`, soma positivos e negativos por linha, separadamente.
 * Valores não numéricos contam como 0 (o validador já rejeita, mas o render não pode quebrar).
 */
export function yDomainThroughZero(
  rows: Record<string, unknown>[],
  keys: string[],
  stacked = false
): [number, number] {
  let min = 0
  let max = 0
  for (const row of rows) {
    if (stacked) {
      let pos = 0
      let neg = 0
      for (const key of keys) {
        const v = toNumber(row[key])
        if (v >= 0) pos += v
        else neg += v
      }
      if (pos > max) max = pos
      if (neg < min) min = neg
    } else {
      for (const key of keys) {
        const v = toNumber(row[key])
        if (v > max) max = v
        if (v < min) min = v
      }
    }
  }
  return [min, max]
}

function toNumber(value: unknown): number {
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : 0
}

/**
 * Número formatado no locale do usuário. Acima de 10 000 usa notação compacta
 * ("12 mil", "1,2 mi") para o tick não estourar o eixo; abaixo, até 2 casas decimais.
 */
export function formatNumber(value: unknown, locale: string, compact = true): string {
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return String(value ?? '')
  const options: Intl.NumberFormatOptions =
    compact && Math.abs(n) >= 10000
      ? { notation: 'compact', maximumFractionDigits: 1 }
      : { maximumFractionDigits: 2 }
  try {
    return new Intl.NumberFormat(locale, options).format(n)
  } catch {
    return new Intl.NumberFormat(undefined, options).format(n)
  }
}

/** Corta rótulo de categoria para caber no eixo X, com reticências. */
export function truncateLabel(label: unknown, max = 14): string {
  const text = String(label ?? '')
  if (text.length <= max) return text
  return `${text.slice(0, Math.max(1, max - 1)).trimEnd()}…`
}

/**
 * Largura estimada do eixo Y a partir do maior rótulo formatado (≈ 7 px por caractere
 * em 11 px de fonte, mais folga), limitada entre 32 e 72 px.
 */
export function yAxisWidthFor(domain: [number, number], locale: string): number {
  const labels = [domain[0], domain[1]].map((v) => formatNumber(v, locale))
  const longest = Math.max(...labels.map((l) => l.length), 1)
  return Math.min(72, Math.max(32, longest * 7 + 10))
}

/** Verdadeiro quando o texto "parece número" (facts de cartão: "R$ 1.200", "42%", "3,5"). */
export function looksNumeric(value: unknown): boolean {
  const text = String(value ?? '').trim()
  if (!text) return false
  return /^[-+]?[^\d]{0,4}\d[\d.,\s]*\s*[%a-zA-Z°]{0,4}$/.test(text)
}

/**
 * CSV dos dados do gráfico (ação "Copiar dados"): cabeçalho com x_key e rótulos das
 * séries, uma linha por `row`. Células com vírgula, aspas ou quebra de linha vão entre aspas.
 */
export function chartToCsv(
  xKey: string,
  series: { key: string; label?: string }[],
  rows: Record<string, unknown>[]
): string {
  const header = [xKey, ...series.map((s) => s.label || s.key)]
  const lines = [header, ...rows.map((row) => [row[xKey], ...series.map((s) => row[s.key])])]
  return lines.map((cells) => cells.map(csvCell).join(',')).join('\n')
}

function csvCell(value: unknown): string {
  const text = value === undefined || value === null ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
