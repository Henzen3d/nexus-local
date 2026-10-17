/**
 * Auditoria de Usabilidade — NexusLocal
 * Fase 0: linha de base antes de qualquer mudança.
 *
 * 8 fluxos obrigatórios + Nielsen + acessibilidade.
 * Usa page.route() para mockar API e context.setOffline() para offline.
 * Zero alteração em código de produto.
 */
import { test, expect, Page, BrowserContext } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

const BASE = 'http://localhost:5173'
const API_BASE = 'https://api-multi.mob.tec.br'
const SCREENSHOTS = 'melhorias/usabilidade/screenshots/baseline'

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function setupApiMocks (context: BrowserContext) {
  await context.route(`${API_BASE}/api/**`, async (route) => {
    const url = route.request().url()

    if (url.includes('/memory/profile') || url.includes('/api/me')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'test-user-001', username: 'testuser', display_name: 'Test User', role: 'user' }) })
    }
    if (url.includes('/api/conversations')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/admin/models')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([{ id: 'agnes', name: 'Agnes' }]) })
    }
    if (url.includes('/api/admin/providers')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) })
    }
    if (url.includes('/api/chat') || url.includes('/api/run')) {
      return route.fulfill({ status: 200, contentType: 'text/event-stream', body: 'data: {"type":"done"}\n\n' })
    }
    if (url.includes('/api/web_search')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ results: [
        { title: 'Resultado 1', url: 'https://exemplo.com/1', snippet: 'Snippet 1' },
        { title: 'Resultado 2', url: 'https://exemplo.com/2', snippet: 'Snippet 2' },
      ] }) })
    }
    // Other endpoints: return neutral data
    if (url.includes('/api/enhancer') || url.includes('/api/proactive') ||
        url.includes('/api/tts') || url.includes('/api/intelligent-ui') ||
        url.includes('/api/fusion') || url.includes('/api/history') ||
        url.includes('/api/memory/') || url.includes('/api/projects') ||
        url.includes('/api/ranking') || url.includes('/api/storage')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
    }
    // Catch-all: fulfill with 200 for any other endpoint to prevent 404s
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
  })
}

async function setupErrorApi (context: BrowserContext, status: number) {
  await context.route(`${API_BASE}/api/chat**`, async (route) => {
    return route.fulfill({ status, body: JSON.stringify({ error: 'service_unavailable' }) })
  })
  await context.route(`${API_BASE}/api/run**`, async (route) => {
    return route.fulfill({ status, body: JSON.stringify({ error: 'service_unavailable' }) })
  })
}

function screenshotName (flow: string) {
  return `${SCREENSHOTS}/${flow.replace(/\s/g, '_').toLowerCase()}.png`
}

// ─── Setup: auth bypass via addInitScript + API mocks ────────────────────────

test.beforeEach(async ({ page, context }) => {
  // CRITICAL: addInitScript runs BEFORE any page load, so token is present on first fetch
  // We set ALL localStorage keys the app expects for a complete user profile
  await context.addInitScript(() => {
    localStorage.setItem('nexuslocal_token', 'test-dev-token')
    localStorage.setItem('nexuslocal_user', JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }))
    // Keys that the app reads to identify the user session
    localStorage.setItem('nexuslocal_test-user-001_display_name', 'Test User')
    localStorage.setItem('nexuslocal_test-user-001_full_name', '')
    localStorage.setItem('nexuslocal_test-user-001_custom_instructions', '')
    localStorage.setItem('nexuslocal_test-user-001_occupation', '')
  })
  // Set up mocks BEFORE navigating
  await setupApiMocks(context)
  await page.goto(BASE)
  await page.waitForTimeout(2000)
})

// ─── Fluxo 1: Primeira mensagem ──────────────────────────────────────────────

test.describe('Fluxo 1 — Primeira mensagem', () => {
  test('envia mensagem e recebe stream', async ({ page }) => {
    await page.screenshot({ path: screenshotName('01_first_message_load') })

    const input = page.locator('.composer-textarea').first()
    await expect(input).toBeVisible({ timeout: 5000 })

    const startTime = Date.now()
    await input.fill('Olá, teste de usabilidade')
    await input.press('Enter')
    const elapsed = Date.now() - startTime
    console.log(`[Fluxo 1] Tempo até enviar: ${elapsed}ms`)

    // Aguarda o composer ser limpo (mensagem enviada com sucesso)
    await expect(input).toHaveValue('', { timeout: 5000 })
    console.log('[Fluxo 1] ✅ Mensagem enviada (composer limpo)')
  })

  test('composer está habilitado na tela inicial', async ({ page }) => {
    const input = page.locator('.composer-textarea').first()
    await expect(input).toBeVisible()
    const disabled = await input.getAttribute('disabled')
    console.log(`[Fluxo 1] Composer visível, disabled=${disabled}`)
    expect(disabled).toBeNull()
  })
})

// ─── Fluxo 2: Trocar modelo/provedor ─────────────────────────────────────────

test.describe('Fluxo 2 — Trocar modelo/provedor', () => {
  test('seletor de modelo é visível na tela inicial', async ({ page }) => {
    await page.screenshot({ path: screenshotName('02_model_selector') })
    const modelSelector = page.locator('.model-selector').first()
    if (await modelSelector.count() > 0) {
      await modelSelector.screenshot({ path: screenshotName('02_model_selector_visible') })
      console.log('[Fluxo 2] ✅ Seletor de modelo visível')
    } else {
      console.log('[Fluxo 2] ⚠️  Seletor de modelo NÃO encontrado na tela inicial')
      await page.screenshot({ path: screenshotName('02_model_selector_missing') })
    }
  })

  test('toggle de provedor só aparece no ProjectsPanel', async ({ page }) => {
    const providerSelector = page.locator('.provider-selector').first()
    if (await providerSelector.count() > 0) {
      console.log('[Fluxo 2] ⚠️  Seletor de provedor visível fora do ProjectsPanel (inconsistência)')
      await providerSelector.screenshot({ path: screenshotName('02_provider_outside_panel') })
    } else {
      console.log('[Fluxo 2] ✅ Seletor de provedor não exposto na tela inicial')
    }
  })
})

// ─── Fluxo 3: Fusion ─────────────────────────────────────────────────────────

test.describe('Fluxo 3 — Fusion', () => {
  test('botão Fusion é visível e identifica-se', async ({ page }) => {
    const fusionBtn = page.locator('[data-testid="fusion-btn"], button:has-text("Fusion"), button:has-text("Resposta Profunda")').first()
    if (await fusionBtn.count() > 0) {
      await fusionBtn.screenshot({ path: screenshotName('03_fusion_button') })
      console.log('[Fluxo 3] ✅ Botão Fusion encontrado')
    } else {
      console.log('[Fluxo 3] ⚠️  Botão Fusion NÃO encontrado na tela inicial')
      await page.screenshot({ path: screenshotName('03_fusion_missing') })
    }
  })

  test('controles avançados do Fusion estão ocultos no nível simples', async ({ page }) => {
    const advancedControls = page.locator('[data-testid="fusion-advanced"], .fusion-params, input[name="fusion_max_rounds"]').first()
    if (await advancedControls.count() > 0 && await advancedControls.isVisible()) {
      console.log('[Fluxo 3] ⚠️  Controles avançados do Fusion visíveis na tela inicial (poluição)')
      await advancedControls.screenshot({ path: screenshotName('03_fusion_advanced_exposed') })
    } else {
      console.log('[Fluxo 3] ✅ Controles avançados do Fusion ocultos')
    }
  })
})

// ─── Fluxo 4: Busca web ──────────────────────────────────────────────────────

test.describe('Fluxo 4 — Busca web', () => {
  test('WebSearchToggle é visível e clicável', async ({ page }) => {
    const searchToggle = page.locator('[data-testid="web-search-toggle"], button:has-text("Pesquisa"), button:has-text("Web Search"), .web-search-toggle').first()
    if (await searchToggle.count() > 0) {
      await searchToggle.screenshot({ path: screenshotName('04_websearch_toggle') })
      console.log('[Fluxo 4] ✅ WebSearchToggle encontrado')
      await searchToggle.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: screenshotName('04_websearch_toggled') })
    } else {
      console.log('[Fluxo 4] ⚠️  WebSearchToggle NÃO encontrado')
      await page.screenshot({ path: screenshotName('04_websearch_missing') })
    }
  })
})

// ─── Fluxo 5: Anexar arquivo ─────────────────────────────────────────────────

test.describe('Fluxo 5 — Anexar arquivo', () => {
  test('botão de anexo é visível no composer', async ({ page }) => {
    const attachBtn = page.locator('[data-testid="attach-btn"], button:has-text("Anexar"), button:has-text("Attach"), .attachment-button, input[type="file"]').first()
    if (await attachBtn.count() > 0) {
      console.log('[Fluxo 5] ✅ Botão de anexo encontrado')
      await page.screenshot({ path: screenshotName('05_attach_button') })
    } else {
      console.log('[Fluxo 5] ⚠️  Botão de anexo NÃO encontrado')
      await page.screenshot({ path: screenshotName('05_attach_missing') })
    }
  })
})

// ─── Fluxo 6: Erro de API ────────────────────────────────────────────────────

test.describe('Fluxo 6 — Erro de API', () => {
  test('HTTP 429 mostra mensagem humana + ação de recuperação', async ({ page, context }) => {
    await setupErrorApi(context, 429)
    const input = page.locator('.composer-textarea').first()
    await expect(input).toBeVisible({ timeout: 5000 })
    await input.fill('Teste erro 429')
    await input.press('Enter')
    await page.waitForTimeout(2000)
    await page.screenshot({ path: screenshotName('06_error_429') })

    const errorMsg = page.locator('.error-message, .api-error, [role="alert"], .toast, .notification').first()
    if (await errorMsg.count() > 0) {
      const text = await errorMsg.textContent()
      console.log(`[Fluxo 6] Mensagem de erro: "${text}"`)
      if (text.length > 10) {
        console.log('[Fluxo 6] ✅ Mensagem de erro legível encontrada')
      } else {
        console.log('[Fluxo 6] ⚠️  Mensagem de erro muito curta ou vazia')
      }
    } else {
      console.log('[Fluxo 6] ⚠️  Nenhuma mensagem de erro visível (falha silenciosa?)')
    }
  })

  test('HTTP 500 mostra mensagem de falha do servidor', async ({ page, context }) => {
    await setupErrorApi(context, 500)
    const input = page.locator('.composer-textarea').first()
    await expect(input).toBeVisible({ timeout: 5000 })
    await input.fill('Teste erro 500')
    await input.press('Enter')
    await page.waitForTimeout(2000)
    await page.screenshot({ path: screenshotName('06_error_500') })

    const errorMsg = page.locator('.error-message, .api-error, [role="alert"], .toast, .notification').first()
    if (await errorMsg.count() > 0) {
      console.log('[Fluxo 6] ✅ Mensagem de erro 500 visível')
    } else {
      console.log('[Fluxo 6] ⚠️  Falha silenciosa no erro 500')
    }
  })
})

// ─── Fluxo 7: Conexão offline ────────────────────────────────────────────────

test.describe('Fluxo 7 — Offline', () => {
  test('setOffline mostra estado adequado', async ({ browser }) => {
    const context = await browser.newContext()
    await context.addInitScript(() => {
      localStorage.setItem('nexuslocal_token', 'test-dev-token')
      localStorage.setItem('nexuslocal_user', JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }))
      localStorage.setItem('nexuslocal_test-user-001_display_name', 'Test User')
      localStorage.setItem('nexuslocal_test-user-001_full_name', '')
      localStorage.setItem('nexuslocal_test-user-001_custom_instructions', '')
      localStorage.setItem('nexuslocal_test-user-001_occupation', '')
    })
    await context.route(`${API_BASE}/api/**`, async (route) => {
      const url = route.request().url()
      if (url.includes('/memory/profile')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }) })
      return route.continue()
    })
    const offlinePage = await context.newPage()
    await offlinePage.goto(BASE)
    await offlinePage.waitForLoadState('networkidle')
    await offlinePage.waitForTimeout(2000)

    await context.setOffline(true)
    await offlinePage.screenshot({ path: screenshotName('07_offline_page') })

    const offlineIndicator = offlinePage.locator('.offline-indicator, [data-offline], .connection-status').first()
    if (await offlineIndicator.count() > 0) {
      console.log('[Fluxo 7] ✅ Indicador de offline encontrado')
    } else {
      console.log('[Fluxo 7] ⚠️  Nenhum indicador de offline visível')
    }

    const input = offlinePage.locator('.composer-textarea').first()
    if (await input.count() > 0) {
      await input.fill('Teste offline')
      await input.press('Enter')
      await offlinePage.waitForTimeout(1500)
      await offlinePage.screenshot({ path: screenshotName('07_offline_send') })

      const errorMsg = offlinePage.locator('.error-message, .api-error, [role="alert"]').first()
      if (await errorMsg.count() > 0) {
        console.log('[Fluxo 7] ✅ Mensagem de erro offline visível')
      } else {
        console.log('[Fluxo 7] ⚠️  Sem feedback ao tentar enviar offline')
      }
    }
    await context.close()
  })
})

// ─── Fluxo 8: Mobile 375px ───────────────────────────────────────────────────

test.describe('Fluxo 8 — Mobile 375px', () => {
  test('sem scroll horizontal em 375x667', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.screenshot({ path: screenshotName('08_mobile_375') })

    const bodyWidth = await page.evaluate(() => document.body.scrollWidth)
    const viewportWidth = await page.evaluate(() => window.innerWidth)
    console.log(`[Fluxo 8] Body width: ${bodyWidth}px, Viewport: ${viewportWidth}px`)
    if (bodyWidth > viewportWidth + 5) {
      console.log('[Fluxo 8] ⚠️  Scroll horizontal detectado no mobile!')
    } else {
      console.log('[Fluxo 8] ✅ Sem scroll horizontal')
    }
  })

  test('drawer/menu mobile é acessível', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.waitForTimeout(1000)

    // Fechar onboarding de memória se estiver aberto
    const memoryCloseBtn = page.locator('[id="memory-onboarding-title"] button, [role="dialog"] button:has-text("Entendi"), [role="dialog"] button:has-text("Fechar")').first()
    if (await memoryCloseBtn.count() > 0) {
      await memoryCloseBtn.click()
      await page.waitForTimeout(500)
    }

    const hamburger = page.locator('[data-testid="hamburger"], .hamburger, button:has-text("☰"), button:has-text("Menu"), [class*="sidebar-toggle"]').first()
    if (await hamburger.count() > 0) {
      await hamburger.click()
      await page.waitForTimeout(500)
      await page.screenshot({ path: screenshotName('08_mobile_drawer') })
      console.log('[Fluxo 8] ✅ Drawer/menu mobile acessível')
    } else {
      console.log('[Fluxo 8] ⚠️  Botão hamburger não encontrado')
    }
  })

  test('botões não se sobrepõem no mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.waitForTimeout(1000)

    const overlays = await page.evaluate(() => {
      // Exclui touch-target pseudo-elements (não são elementos reais)
      const elements = Array.from(document.querySelectorAll('button, a, [role="button"], input, textarea'))
        .filter(el => !el.classList.contains('touch-target'))
      const overlaps: string[] = []
      for (let i = 0; i < elements.length; i++) {
        for (let j = i + 1; j < elements.length; j++) {
          const r1 = elements[i].getBoundingClientRect()
          const r2 = elements[j].getBoundingClientRect()
          // Ignora sobreposições mínimas (< 5px)
          if (r1.left < r2.right && r1.right > r2.left && r1.top < r2.bottom && r1.bottom > r2.top) {
            const dx = Math.min(r1.right - r2.left, r2.right - r1.left)
            const dy = Math.min(r1.bottom - r2.top, r2.bottom - r1.top)
            if (dx > 5 && dy > 5) {
              overlaps.push(`${elements[i].tagName}.${(elements[i].className || '').toString().split(' ')[0]}`)
            }
          }
        }
      }
      return overlaps
    })
    if (overlays.length > 0) {
      console.log(`[Fluxo 8] ⚠️  ${overlays.length} sobreposições: ${overlays.slice(0, 3).join(', ')}`)
    } else {
      console.log('[Fluxo 8] ✅ Sem sobreposição de botões')
    }
  })

  test('U07: busca web dentro da gaveta + (mobile)', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.waitForTimeout(1000)

    // Fechar onboarding de memória se estiver aberto
    const memoryCloseBtn = page.locator('[id="memory-onboarding-title"] button, [role="dialog"] button:has-text("Entendi"), [role="dialog"] button:has-text("Fechar")').first()
    if (await memoryCloseBtn.count() > 0) {
      await memoryCloseBtn.click()
      await page.waitForTimeout(500)
    }

    // Clicar no + para abrir a gaveta
    const plusBtn = page.locator('.composer-plus-btn').first()
    if (await plusBtn.count() > 0 && await plusBtn.isVisible()) {
      await plusBtn.click({ force: true })
      await page.waitForTimeout(500)
      await page.screenshot({ path: screenshotName('08_plus_drawer') })

      // Verificar se busca web está na gaveta
      const webSearch = page.locator('button:has-text("Pesquisa"), button:has-text("Web Search"), .web-search-toggle').first()
      if (await webSearch.count() > 0) {
        console.log('[U07] ✅ Busca web encontrada na gaveta +')
      } else {
        console.log('[U07] ⚠️  Busca web NÃO encontrada na gaveta +')
      }
    } else {
      console.log('[U07] ⚠️  Botão + não encontrado')
    }
  })

  test('U08: Fusion dentro da gaveta + (mobile)', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.waitForTimeout(1000)

    // Fechar onboarding de memória se estiver aberto
    const memoryCloseBtn = page.locator('[id="memory-onboarding-title"] button, [role="dialog"] button:has-text("Entendi"), [role="dialog"] button:has-text("Fechar")').first()
    if (await memoryCloseBtn.count() > 0) {
      await memoryCloseBtn.click()
      await page.waitForTimeout(500)
    }

    // Clicar no + para abrir a gaveta
    const plusBtn = page.locator('.composer-plus-btn').first()
    if (await plusBtn.count() > 0 && await plusBtn.isVisible()) {
      await plusBtn.click({ force: true })
      await page.waitForTimeout(500)

      // Verificar se Fusion está na gaveta
      const fusionBtn = page.locator('button:has-text("Fusion"), button:has-text("Resposta Profunda"), .fusion-toggle').first()
      if (await fusionBtn.count() > 0) {
        console.log('[U08] ✅ Fusion encontrado na gaveta +')
      } else {
        console.log('[U08] ⚠️  Fusion NÃO encontrado na gaveta +')
      }
    } else {
      console.log('[U08] ⚠️  Botão + não encontrado')
    }
  })
})

// ─── U01: Erros de API com retry ─────────────────────────────────────────────

test.describe('U01 — feedback de erro de API + retry', () => {
  test('toast de erro exibe botão "Tentar novamente"', async ({ page }) => {
    // Mock WebSocket error
    await page.route('wss://api-multi.mob.tec.br/ws/chat*', async (route) => {
      // Aceita a conexão WS mas depois envia erro
      const ws = route.request().url()
      route.fulfill({ status: 200, body: '' })
    })

    // Navega e aguarda carregar
    await page.goto(BASE)
    await page.waitForTimeout(2000)

    // Fecha onboarding
    const closeBtn = page.locator('[id="memory-onboarding-title"] button').first()
    if (await closeBtn.count() > 0) await closeBtn.click()
    await page.waitForTimeout(500)

    // Envia mensagem
    await page.fill('.composer-textarea', 'teste erro u01')
    await page.keyboard.press('Enter')
    await page.waitForTimeout(1000)

    // Verifica se toast de erro aparece com ação de retry
    const errorToast = page.locator('.toast-container.toast-error').first()
    if (await errorToast.count() > 0) {
      const hasRetry = await errorToast.locator('button:has-text("Tentar novamente")').count() > 0
      if (hasRetry) {
        console.log('[U01] ✅ Toast de erro com botão "Tentar novamente" encontrado')
      } else {
        console.log('[U01] ⚠️  Toast de erro sem botão retry')
      }
    } else {
      console.log('[U01] ℹ️  Nenhum toast de erro gerado (erro não simulado no mock)')
    }
  })
})

// ─── U02: Detecção offline ────────────────────────────────────────────────────

test.describe('U02 — detecção offline', () => {
  test('banner offline aparece quando desconectado', async ({ page, context }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto(BASE)
    await page.waitForTimeout(2000)

    // Fecha onboarding
    const closeBtn = page.locator('[id="memory-onboarding-title"] button').first()
    if (await closeBtn.count() > 0) await closeBtn.click()
    await page.waitForTimeout(500)

    // Simula offline
    await context.setOffline(true)
    await page.waitForTimeout(1000)

    const banner = page.locator('.offline-banner')
    if (await banner.count() > 0 && await banner.isVisible()) {
      console.log('[U02] ✅ Banner offline visível')
      await page.screenshot({ path: screenshotName('09_offline_banner') })
    } else {
      console.log('[U02] ⚠️  Banner offline NÃO encontrado')
    }

    // Restaura online
    await context.setOffline(false)
    await page.waitForTimeout(500)
  })

  test('banner some ao reconectar', async ({ page, context }) => {
    await page.setViewportSize({ width: 1280, height: 800 })
    await page.goto(BASE)
    await page.waitForTimeout(2000)

    const closeBtn = page.locator('[id="memory-onboarding-title"] button').first()
    if (await closeBtn.count() > 0) await closeBtn.click()
    await page.waitForTimeout(500)

    // Vai offline e volta
    await context.setOffline(true)
    await page.waitForTimeout(500)
    await context.setOffline(false)
    await page.waitForTimeout(1000)

    const banner = page.locator('.offline-banner')
    const isVisible = await banner.count() > 0 && await banner.isVisible()
    if (!isVisible) {
      console.log('[U02] ✅ Banner some ao reconectar')
    } else {
      console.log('[U02] ⚠️  Banner permanece visível após reconectar')
    }
  })
})

// ─── Acessibilidade: axe ──────────────────────────────────────────────────────

test.describe('Acessibilidade — axe', () => {
  test('violacoes críticas na tela inicial', async ({ page }) => {
    const results = await new AxeBuilder({ page }).analyze()

    const critical = results.violations.filter((v: any) => v.impact === 'critical')
    const serious = results.violations.filter((v: any) => v.impact === 'serious')
    console.log(`[Acessibilidade] Críticas: ${critical.length}, Sérias: ${serious.length}`)

    for (const v of critical) {
      console.log(`  🔴 CRÍTICO: ${v.id} — ${v.description}`)
      console.log(`     Impacto: ${v.impact} | Elements: ${v.nodes.length}`)
    }
    for (const v of serious) {
      console.log(`  🟠 SÉRIO: ${v.id} — ${v.description}`)
    }

    const fs = await import('fs')
    fs.writeFileSync('melhorias/usabilidade/axe-initial.json', JSON.stringify(results, null, 2))
    console.log('[Acessibilidade] Resultados salvos em axe-initial.json')

    expect(critical.length).toBeLessThan(10)
  })

  test('foco de teclado no composer', async ({ page }) => {
    // Navigate through tabs to reach composer
    for (let i = 0; i < 15; i++) {
      await page.keyboard.press('Tab')
      await page.waitForTimeout(200)
    }
    await page.waitForTimeout(500)
    await page.screenshot({ path: screenshotName('a11y_focus_composer') })

    const focused = await page.evaluate(() => {
      const el = document.activeElement
      return el ? el.tagName + '.' + ((el.className || '').toString().split(' ')[0] || '') : 'none'
    })
    console.log(`[A11Y] Foco após 15 Tabs: ${focused}`)

    // Check if focused element is the composer
    const composerFocused = await page.locator('.composer-textarea:focus').count()
    if (composerFocused > 0) {
      console.log('[A11Y] ✅ Foco alcança o composer via teclado')
    } else {
      console.log('[A11Y] ⚠️  Foco não alcança o composer (procurar alternativa)')
    }
  })
})

// ─── Heurísticas de Nielsen ──────────────────────────────────────────────────

test.describe('Heurísticas de Nielsen', () => {
  test('visibilidade do status do sistema', async ({ page }) => {
    const loadingIndicators = page.locator('.loading, .spinner, [aria-busy="true"], .status-indicator').first()
    if (await loadingIndicators.count() > 0) {
      console.log('[Nielsen] ✅ Indicador de status carregando presente')
    } else {
      console.log('[Nielsen] ⚠️  Nenhum indicador de loading visível na tela inicial')
    }
  })

  test('rotulos visiveis nos botoes', async ({ page }) => {
    const buttons = await page.locator('button').all()
    let emptyLabels = 0
    for (const btn of buttons.slice(0, 10)) {
      const text = await btn.textContent()
      const ariaLabel = await btn.getAttribute('aria-label')
      if (!text?.trim() && !ariaLabel) emptyLabels++
    }
    console.log(`[Nielsen] ${emptyLabels}/10 botoes sem label visivel nem aria-label`)
    if (emptyLabels > 2) {
      console.log('[Nielsen] ⚠️  Muitos botoes sem labels (viola reconhecimento)')
    } else {
      console.log('[Nielsen] ✅ botoes com labels adequados')
    }
  })
})

// ─── Otica dos 3 niveis de UI ────────────────────────────────────────────────

test.describe('Niveis de UI — poluicao visual no nivel Simples', () => {
  test('controles tecnicos expostos indevidamente na tela inicial', async ({ page }) => {
    const technicalControls = [
      { selector: '.provider-selector', name: 'Seletor de Provedor' },
      { selector: '.admin-panel, [data-testid="admin"]', name: 'Admin Panel' },
      { selector: '.memory-panel, [data-testid="user-memory"]', name: 'User Memory Panel' },
      { selector: '.fusion-params, [data-testid="fusion-advanced"]', name: 'Parametros Fusion' },
      { selector: '.reasoning-controls, [data-testid="reasoning-manual"]', name: 'Reasoning manual' },
      { selector: '.project-panels, [data-testid="projects"]', name: 'Projetos/RAG' },
    ]

    const exposed: string[] = []
    for (const { selector, name } of technicalControls) {
      const el = page.locator(selector).first()
      if (await el.count() > 0 && await el.isVisible()) {
        exposed.push(name)
      }
    }

    if (exposed.length > 0) {
      console.log(`[Niveis UI] ⚠️  ${exposed.length} controles tecnicos expostos no nivel Simples: ${exposed.join(', ')}`)
    } else {
      console.log('[Niveis UI] ✅ Nenhum controle tecnico exposto na tela inicial')
    }

    await page.screenshot({ path: screenshotName('ui_levels_pollution') })
  })

  test('sidebar contem muitos itens para usuario simples', async ({ page }) => {
    const sidebarItems = await page.locator('.sidebar-item, [class*="sidebar"] li, [class*="nav"] li').count()
    console.log(`[Niveis UI] Itens na sidebar: ${sidebarItems}`)
    if (sidebarItems > 10) {
      console.log('[Niveis UI] ⚠️  Sidebar com muitos itens (poluicao para nivel Simples)')
    } else {
      console.log('[Niveis UI] ✅ Sidebar com quantidade razoavel de itens')
    }
  })
})
