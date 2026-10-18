import { test, expect, BrowserContext } from '@playwright/test'

const BASE = 'http://localhost:5173'
const API_BASE = 'https://api-multi.mob.tec.br'
const SCREENSHOTS = 'melhorias/usabilidade/screenshots/depois'

test.describe('UiLevelSelector - 3 Níveis de Interface', () => {
  test.beforeEach(async ({ page, context }) => {
    // Setup auth como no auditoria.spec.ts
    await context.addInitScript(() => {
      localStorage.setItem('nexuslocal_token', 'test-dev-token')
      localStorage.setItem('nexuslocal_user', JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }))
      localStorage.setItem('nexuslocal_test-user-001_display_name', 'Test User')
      localStorage.setItem('nexuslocal_test-user-001_full_name', '')
      localStorage.setItem('nexuslocal_test-user-001_custom_instructions', '')
      localStorage.setItem('nexuslocal_test-user-001_occupation', '')
    })

    // Mock API
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
      if (url.includes('/api/enhancer') || url.includes('/api/proactive') ||
          url.includes('/api/tts') || url.includes('/api/intelligent-ui') ||
          url.includes('/api/fusion') || url.includes('/api/history') ||
          url.includes('/api/memory/') || url.includes('/api/projects') ||
          url.includes('/api/ranking') || url.includes('/api/storage')) {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
      }
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) })
    })

    await page.goto(BASE)
    await page.waitForTimeout(2000)
  })

  test('deve exibir seletor de nível na sidebar', async ({ page }) => {
    await expect(page.locator('.ui-level-selector')).toBeVisible()
    await expect(page.locator('.ui-level-btn')).toHaveCount(3)
  })

  test('deve ter botões "Simples", "Intermediário" e "Avançado"', async ({ page }) => {
    const buttons = page.locator('.ui-level-btn')
    await expect(buttons.nth(0)).toContainText('Simples')
    await expect(buttons.nth(1)).toContainText('Intermediario')
    await expect(buttons.nth(2)).toContainText('Avancado')
  })

  test('deve iniciar no nível "Simples" (padrão)', async ({ page }) => {
    const activeBtn = page.locator('.ui-level-btn.active')
    await expect(activeBtn).toBeVisible()
    await expect(activeBtn).toContainText('Simples')
  })

  test('deve alternar para "Intermediário" ao clicar', async ({ page }) => {
    // Usa evaluate para clicar diretamente no botão via JS
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('.ui-level-btn')
      if (buttons[1]) (buttons[1] as HTMLButtonElement).click()
    })
    await page.waitForTimeout(300)
    const activeText = await page.locator('.ui-level-btn.active').textContent()
    expect(activeText).toContain('Intermediario')
  })

  test('deve alternar para "Avançado" ao clicar', async ({ page }) => {
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('.ui-level-btn')
      if (buttons[2]) (buttons[2] as HTMLButtonElement).click()
    })
    await page.waitForTimeout(300)
    const activeText = await page.locator('.ui-level-btn.active').textContent()
    expect(activeText).toContain('Avancado')
  })

  test('deve persistir nível selecionado no localStorage', async ({ page }) => {
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('.ui-level-btn')
      if (buttons[1]) (buttons[1] as HTMLButtonElement).click()
    })
    await page.waitForTimeout(300)
    const stored = await page.evaluate(() => localStorage.getItem('nexuslocal_ui_level'))
    expect(stored).toBe('intermediate')
  })

  test('deve restaurar nível do localStorage ao recarregar', async ({ page }) => {
    await page.evaluate(() => {
      const buttons = document.querySelectorAll('.ui-level-btn')
      if (buttons[2]) (buttons[2] as HTMLButtonElement).click()
    })
    await page.waitForTimeout(300)
    await page.reload()
    await page.waitForTimeout(2000)
    const activeText = await page.locator('.ui-level-btn.active').textContent()
    expect(activeText).toContain('Avancado')
  })

  test('deve capturar screenshot do seletor em todos os níveis', async ({ page }) => {
    const levels = ['simple', 'intermediate', 'advanced'] as const
    const labels = ['Simples', 'Intermediario', 'Avancado']

    for (let i = 0; i < levels.length; i++) {
      // Clicar no botão correspondente via JS
      await page.evaluate((idx: number) => {
        const buttons = document.querySelectorAll('.ui-level-btn')
        if (buttons[idx]) (buttons[idx] as HTMLButtonElement).click()
      }, i)

      await page.waitForTimeout(300)

      // Captura screenshot
      await page.screenshot({ path: `${SCREENSHOTS}/ui-level-${levels[i]}.png` })
    }
  })
})
