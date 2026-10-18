# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: melhorias/usabilidade/auditoria.spec.ts >> Fluxo 1 — Primeira mensagem >> envia mensagem e recebe stream
- Location: melhorias/usabilidade/auditoria.spec.ts:92:7

# Error details

```
Error: expect(locator).toHaveValue(expected) failed

Locator:  locator('.composer-textarea').first()
Expected: ""
Received: "Olá, teste de usabilidade"
Timeout:  5000ms

Call log:
  - Expect "toHaveValue" locator('.composer-textarea').first() with timeout 5000ms
  - waiting for locator('.composer-textarea').first()
    14 × locator resolved to <textarea rows="1" enterkeyhint="send" class="composer-textarea " placeholder="Pick a model in the selector to get started…">Olá, teste de usabilidade</textarea>
       - unexpected value "Olá, teste de usabilidade"

```

```yaml
- textbox "Pick a model in the selector to get started…": Olá, teste de usabilidade
```

# Test source

```ts
  5   |  * 8 fluxos obrigatórios + Nielsen + acessibilidade.
  6   |  * Usa page.route() para mockar API e context.setOffline() para offline.
  7   |  * Zero alteração em código de produto.
  8   |  */
  9   | import { test, expect, Page, BrowserContext } from '@playwright/test'
  10  | import AxeBuilder from '@axe-core/playwright'
  11  | 
  12  | const BASE = 'http://localhost:5173'
  13  | const API_BASE = 'https://api-multi.mob.tec.br'
  14  | const SCREENSHOTS = 'melhorias/usabilidade/screenshots/baseline'
  15  | 
  16  | // ─── Helpers ─────────────────────────────────────────────────────────────────
  17  | 
  18  | async function setupApiMocks (context: BrowserContext) {
  19  |   await context.route(`${API_BASE}/api/**`, async (route) => {
  20  |     const url = route.request().url()
  21  | 
  22  |     if (url.includes('/memory/profile') || url.includes('/api/me')) {
  23  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'test-user-001', username: 'testuser', display_name: 'Test User', role: 'user' }) })
  24  |     }
  25  |     if (url.includes('/api/conversations')) {
  26  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  27  |     }
  28  |     if (url.includes('/api/admin/models')) {
  29  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 'agnes', name: 'Agnes' }]) })
  30  |     }
  31  |     if (url.includes('/api/admin/providers')) {
  32  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
  33  |     }
  34  |     if (url.includes('/api/chat') || url.includes('/api/run')) {
  35  |       return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"done"}\n\n' })
  36  |     }
  37  |     if (url.includes('/api/web_search')) {
  38  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [
  39  |         { title: 'Resultado 1', url: 'https://exemplo.com/1', snippet: 'Snippet 1' },
  40  |         { title: 'Resultado 2', url: 'https://exemplo.com/2', snippet: 'Snippet 2' },
  41  |       ] }) })
  42  |     }
  43  |     // Other endpoints: return neutral data
  44  |     if (url.includes('/api/enhancer') || url.includes('/api/proactive') ||
  45  |         url.includes('/api/tts') || url.includes('/api/intelligent-ui') ||
  46  |         url.includes('/api/fusion') || url.includes('/api/history') ||
  47  |         url.includes('/api/memory/') || url.includes('/api/projects') ||
  48  |         url.includes('/api/ranking') || url.includes('/api/storage')) {
  49  |       return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  50  |     }
  51  |     // Catch-all: fulfill with 200 for any other endpoint to prevent 404s
  52  |     return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  53  |   })
  54  | }
  55  | 
  56  | async function setupErrorApi (context: BrowserContext, status: number) {
  57  |   await context.route(`${API_BASE}/api/chat**`, async (route) => {
  58  |     return route.fulfill({ status, body: JSON.stringify({ error: 'service_unavailable' }) })
  59  |   })
  60  |   await context.route(`${API_BASE}/api/run**`, async (route) => {
  61  |     return route.fulfill({ status, body: JSON.stringify({ error: 'service_unavailable' }) })
  62  |   })
  63  | }
  64  | 
  65  | function screenshotName (flow: string) {
  66  |   return `${SCREENSHOTS}/${flow.replace(/\s/g, '_').toLowerCase()}.png`
  67  | }
  68  | 
  69  | // ─── Setup: auth bypass via addInitScript + API mocks ────────────────────────
  70  | 
  71  | test.beforeEach(async ({ page, context }) => {
  72  |   // CRITICAL: addInitScript runs BEFORE any page load, so token is present on first fetch
  73  |   // We set ALL localStorage keys the app expects for a complete user profile
  74  |   await context.addInitScript(() => {
  75  |     localStorage.setItem('nexuslocal_token', 'test-dev-token')
  76  |     localStorage.setItem('nexuslocal_user', JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }))
  77  |     // Keys that the app reads to identify the user session
  78  |     localStorage.setItem('nexuslocal_test-user-001_display_name', 'Test User')
  79  |     localStorage.setItem('nexuslocal_test-user-001_full_name', '')
  80  |     localStorage.setItem('nexuslocal_test-user-001_custom_instructions', '')
  81  |     localStorage.setItem('nexuslocal_test-user-001_occupation', '')
  82  |   })
  83  |   // Set up mocks BEFORE navigating
  84  |   await setupApiMocks(context)
  85  |   await page.goto(BASE)
  86  |   await page.waitForTimeout(2000)
  87  | })
  88  | 
  89  | // ─── Fluxo 1: Primeira mensagem ──────────────────────────────────────────────
  90  | 
  91  | test.describe('Fluxo 1 — Primeira mensagem', () => {
  92  |   test('envia mensagem e recebe stream', async ({ page }) => {
  93  |     await page.screenshot({ path: screenshotName('01_first_message_load') })
  94  | 
  95  |     const input = page.locator('.composer-textarea').first()
  96  |     await expect(input).toBeVisible({ timeout: 5000 })
  97  | 
  98  |     const startTime = Date.now()
  99  |     await input.fill('Olá, teste de usabilidade')
  100 |     await input.press('Enter')
  101 |     const elapsed = Date.now() - startTime
  102 |     console.log(`[Fluxo 1] Tempo até enviar: ${elapsed}ms`)
  103 | 
  104 |     // Aguarda o composer ser limpo (mensagem enviada com sucesso)
> 105 |     await expect(input).toHaveValue('', { timeout: 5000 })
      |                         ^ Error: expect(locator).toHaveValue(expected) failed
  106 |     console.log('[Fluxo 1] ✅ Mensagem enviada (composer limpo)')
  107 |   })
  108 | 
  109 |   test('composer está habilitado na tela inicial', async ({ page }) => {
  110 |     const input = page.locator('.composer-textarea').first()
  111 |     await expect(input).toBeVisible()
  112 |     const disabled = await input.getAttribute('disabled')
  113 |     console.log(`[Fluxo 1] Composer visível, disabled=${disabled}`)
  114 |     expect(disabled).toBeNull()
  115 |   })
  116 | })
  117 | 
  118 | // ─── Fluxo 2: Trocar modelo/provedor ─────────────────────────────────────────
  119 | 
  120 | test.describe('Fluxo 2 — Trocar modelo/provedor', () => {
  121 |   test('seletor de modelo é visível na tela inicial', async ({ page }) => {
  122 |     await page.screenshot({ path: screenshotName('02_model_selector') })
  123 |     const modelSelector = page.locator('.model-selector').first()
  124 |     if (await modelSelector.count() > 0) {
  125 |       await modelSelector.screenshot({ path: screenshotName('02_model_selector_visible') })
  126 |       console.log('[Fluxo 2] ✅ Seletor de modelo visível')
  127 |     } else {
  128 |       console.log('[Fluxo 2] ⚠️  Seletor de modelo NÃO encontrado na tela inicial')
  129 |       await page.screenshot({ path: screenshotName('02_model_selector_missing') })
  130 |     }
  131 |   })
  132 | 
  133 |   test('toggle de provedor só aparece no ProjectsPanel', async ({ page }) => {
  134 |     const providerSelector = page.locator('.provider-selector').first()
  135 |     if (await providerSelector.count() > 0) {
  136 |       console.log('[Fluxo 2] ⚠️  Seletor de provedor visível fora do ProjectsPanel (inconsistência)')
  137 |       await providerSelector.screenshot({ path: screenshotName('02_provider_outside_panel') })
  138 |     } else {
  139 |       console.log('[Fluxo 2] ✅ Seletor de provedor não exposto na tela inicial')
  140 |     }
  141 |   })
  142 | })
  143 | 
  144 | // ─── Fluxo 3: Fusion ─────────────────────────────────────────────────────────
  145 | 
  146 | test.describe('Fluxo 3 — Fusion', () => {
  147 |   test('botão Fusion é visível e identifica-se', async ({ page }) => {
  148 |     const fusionBtn = page.locator('[data-testid="fusion-btn"], button:has-text("Fusion"), button:has-text("Resposta Profunda")').first()
  149 |     if (await fusionBtn.count() > 0) {
  150 |       await fusionBtn.screenshot({ path: screenshotName('03_fusion_button') })
  151 |       console.log('[Fluxo 3] ✅ Botão Fusion encontrado')
  152 |     } else {
  153 |       console.log('[Fluxo 3] ⚠️  Botão Fusion NÃO encontrado na tela inicial')
  154 |       await page.screenshot({ path: screenshotName('03_fusion_missing') })
  155 |     }
  156 |   })
  157 | 
  158 |   test('controles avançados do Fusion estão ocultos no nível simples', async ({ page }) => {
  159 |     const advancedControls = page.locator('[data-testid="fusion-advanced"], .fusion-params, input[name="fusion_max_rounds"]').first()
  160 |     if (await advancedControls.count() > 0 && await advancedControls.isVisible()) {
  161 |       console.log('[Fluxo 3] ⚠️  Controles avançados do Fusion visíveis na tela inicial (poluição)')
  162 |       await advancedControls.screenshot({ path: screenshotName('03_fusion_advanced_exposed') })
  163 |     } else {
  164 |       console.log('[Fluxo 3] ✅ Controles avançados do Fusion ocultos')
  165 |     }
  166 |   })
  167 | })
  168 | 
  169 | // ─── Fluxo 4: Busca web ──────────────────────────────────────────────────────
  170 | 
  171 | test.describe('Fluxo 4 — Busca web', () => {
  172 |   test('WebSearchToggle é visível e clicável', async ({ page }) => {
  173 |     const searchToggle = page.locator('[data-testid="web-search-toggle"], button:has-text("Pesquisa"), button:has-text("Web Search"), .web-search-toggle').first()
  174 |     if (await searchToggle.count() > 0) {
  175 |       await searchToggle.screenshot({ path: screenshotName('04_websearch_toggle') })
  176 |       console.log('[Fluxo 4] ✅ WebSearchToggle encontrado')
  177 |       await searchToggle.click()
  178 |       await page.waitForTimeout(500)
  179 |       await page.screenshot({ path: screenshotName('04_websearch_toggled') })
  180 |     } else {
  181 |       console.log('[Fluxo 4] ⚠️  WebSearchToggle NÃO encontrado')
  182 |       await page.screenshot({ path: screenshotName('04_websearch_missing') })
  183 |     }
  184 |   })
  185 | })
  186 | 
  187 | // ─── Fluxo 5: Anexar arquivo ─────────────────────────────────────────────────
  188 | 
  189 | test.describe('Fluxo 5 — Anexar arquivo', () => {
  190 |   test('botão de anexo é visível no composer', async ({ page }) => {
  191 |     const attachBtn = page.locator('[data-testid="attach-btn"], button:has-text("Anexar"), button:has-text("Attach"), .attachment-button, input[type="file"]').first()
  192 |     if (await attachBtn.count() > 0) {
  193 |       console.log('[Fluxo 5] ✅ Botão de anexo encontrado')
  194 |       await page.screenshot({ path: screenshotName('05_attach_button') })
  195 |     } else {
  196 |       console.log('[Fluxo 5] ⚠️  Botão de anexo NÃO encontrado')
  197 |       await page.screenshot({ path: screenshotName('05_attach_missing') })
  198 |     }
  199 |   })
  200 | })
  201 | 
  202 | // ─── Fluxo 6: Erro de API ────────────────────────────────────────────────────
  203 | 
  204 | test.describe('Fluxo 6 — Erro de API', () => {
  205 |   test('HTTP 429 mostra mensagem humana + ação de recuperação', async ({ page, context }) => {
```