import { test, expect } from '@playwright/test'
import path from 'path'

const BASE = 'http://localhost:5173'
const SCREENSHOTS_DIR = path.join('melhorias', 'projetos', 'screenshots')

test.describe('PROJETOS - Paridade Completa Claude.ai (E2E)', () => {
  // In-memory state for mock API
  let projects: any[] = []
  let projectFiles: Record<string, any[]> = {}
  let projectChats: Record<string, any[]> = {}
  let lastPromptPayload: any = null

  test.beforeEach(async ({ page, context }) => {
    // Reset state before each test
    projects = [
      {
        id: 'proj-esp32',
        name: 'Projeto Robô ESP32',
        description: 'Firmware, pinout e controle de servomotores do robô bípede',
        instructions: 'Responda sempre como engenheiro de sistemas embarcados focado em ESP-IDF e C++.',
        is_favorite: 0,
        memory: null,
        file_count: 0,
        updated_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
        capacity: {
          total_tokens: 28,
          capacity_limit: 131072,
          usage_percent: 1,
          mode: 'full',
          breakdown: {
            instructions_tokens: 28,
            memory_tokens: 0,
            files_tokens: 0,
            file_count: 0,
          },
        },
      },
    ]

    projectFiles = {
      'proj-esp32': [],
      'proj-b': [],
    }

    projectChats = {
      'proj-esp32': [
        {
          id: 'chat-esp-01',
          project_id: 'proj-esp32',
          title: 'Configuração dos pinos PWM',
          updated_at: new Date(Date.now() - 3600000).toISOString(),
          created_at: new Date(Date.now() - 3600000).toISOString(),
        },
      ],
      'proj-b': [],
    }

    lastPromptPayload = null

    // Setup local storage auth
    await context.addInitScript(() => {
      localStorage.setItem('nexuslocal_token', 'test-dev-token')
      localStorage.setItem('nexuslocal_user', JSON.stringify({ id: 'test-user-001', username: 'testuser', role: 'user' }))
      localStorage.setItem('nexuslocal_test-user-001_display_name', 'Test User')
      localStorage.setItem('nexuslocal_ui_level', 'intermediate')
      localStorage.setItem('nexuslocal_locale', 'pt-BR')
      localStorage.setItem('i18nextLng', 'pt-BR')
      localStorage.setItem('nexuslocal_memory_onboarding_seen', '1')
    })

    // Setup API interceptors
    await context.route('**/api/**', async (route) => {
      const req = route.request()
      const url = req.url()
      const method = req.method()
      // Ignore Vite source and bundle files
      if (url.includes('/src/') || url.includes('/node_modules/') || url.includes('@') || url.includes('?t=')) {
        return route.continue()
      }

      // Me & user profile
      if (url.includes('/api/me') || url.includes('/api/memory/profile')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'test-user-001',
            username: 'testuser',
            display_name: 'Test User',
            role: 'user',
          }),
        })
      }

      if (url.includes('/api/conversations')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([]),
        })
      }

      // Models & providers
      if (url.includes('/api/admin/models')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            { id: 'agnes', name: 'Agnes', display_name: 'Agnes', provider: 'openai' },
            { id: 'gpt-4o', name: 'GPT-4o', display_name: 'GPT-4o', provider: 'openai' },
          ]),
        })
      }
      if (url.includes('/api/admin/providers')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([{ id: 'openai', name: 'OpenAI', is_active: 1 }]),
        })
      }

      // Projects endpoints
      if (url.includes('/api/projects')) {
        const pathname = new URL(url).pathname
        const sub = pathname.replace(/^\/api\/projects\/?/, '')
        const parts = sub ? sub.split('/') : []
        const pid = parts[0] || ''

        // GET or POST /api/projects
        if (parts.length === 0) {
          if (method === 'POST') {
            let bodyData: any = {}
            try {
              bodyData = req.postDataJSON()
            } catch {
              /* ignore */
            }
            const newProj = {
              id: `proj-${Date.now()}`,
              name: bodyData.name || 'Novo Projeto',
              description: bodyData.description || '',
              instructions: bodyData.instructions || '',
              is_favorite: 0,
              memory: null,
              file_count: 0,
              updated_at: new Date().toISOString(),
              created_at: new Date().toISOString(),
              capacity: {
                total_tokens: 0,
                capacity_limit: 131072,
                usage_percent: 0,
                mode: 'full',
                breakdown: {
                  instructions_tokens: 0,
                  memory_tokens: 0,
                  files_tokens: 0,
                  file_count: 0,
                },
              },
            }
            projects.unshift(newProj)
            projectFiles[newProj.id] = []
            projectChats[newProj.id] = []
            return route.fulfill({
              status: 201,
              contentType: 'application/json',
              body: JSON.stringify(newProj),
            })
          }
          // GET list
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(projects),
          })
        }

        // Sub-routes for /api/projects/:pid/...
        // 1. Capacity: /api/projects/:pid/capacity
        if (parts[1] === 'capacity') {
          const proj = projects.find((p) => p.id === pid)
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(
              proj?.capacity || {
                total_tokens: 0,
                capacity_limit: 131072,
                usage_percent: 0,
                mode: 'full',
                breakdown: { instructions_tokens: 0, memory_tokens: 0, files_tokens: 0, file_count: 0 },
              }
            ),
          })
        }

        // 2. Synthesize memory: /api/projects/:pid/memory/synthesize
        if (parts[1] === 'memory' && parts[2] === 'synthesize') {
          const proj = projects.find((p) => p.id === pid)
          const newMem = {
            project_id: pid,
            summary_text:
              'Fatos consolidados do projeto: O robô utiliza ponte H L298N, servomotores MG996R com controle via WebSockets e loop de controle a 50Hz.',
            updated_at: new Date().toISOString(),
            scope_badge: 'Apenas você',
          }
          if (proj) proj.memory = newMem
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify(newMem),
          })
        }

        // 3. Files: /api/projects/:pid/files and /api/projects/:pid/files/:fid
        if (parts[1] === 'files') {
          if (parts[3] === 'details') {
            const f = (projectFiles[pid] || []).find((x) => x.id === parts[2])
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({
                ...(f || {}),
                extracted_text: f?.extracted_text || '# Manual de Motores ESP32\n\nEspecificações de corrente: 1.2A máximo.',
              }),
            })
          }

          if (parts[3] === 'content') {
            return route.fulfill({
              status: 200,
              contentType: 'text/plain',
              body: '# Raw Manual de Motores ESP32',
            })
          }

          if (parts[2] && method === 'DELETE') {
            const fid = parts[2]
            if (projectFiles[pid]) {
              projectFiles[pid] = projectFiles[pid].filter((f) => f.id !== fid)
            }
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({ ok: true }),
            })
          }

          if (method === 'GET') {
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(projectFiles[pid] || []),
            })
          }

          if (method === 'POST') {
            const files = projectFiles[pid] || []
            if (files.some((f) => f.filename === 'manual_motores.md')) {
              return route.fulfill({
                status: 409,
                contentType: 'application/json',
                body: JSON.stringify({
                  detail: "Arquivo duplicado: 'manual_motores.md' já existe neste projeto (mesmo conteúdo).",
                }),
              })
            }

            const newFile = {
              id: `file-${Date.now()}`,
              project_id: pid,
              filename: 'manual_motores.md',
              file_size: 2840,
              token_count: 710,
              index_status: 'ready',
              created_at: new Date().toISOString(),
            }
            files.push(newFile)
            projectFiles[pid] = files

            const proj = projects.find((p) => p.id === pid)
            if (proj) {
              proj.file_count = files.length
              proj.capacity.breakdown.files_tokens += 710
              proj.capacity.breakdown.file_count = files.length
              proj.capacity.total_tokens += 710
              proj.capacity.usage_percent = Math.min(
                100,
                Math.round((proj.capacity.total_tokens / proj.capacity.capacity_limit) * 100)
              )
            }

            return route.fulfill({
              status: 201,
              contentType: 'application/json',
              body: JSON.stringify(newFile),
            })
          }
        }

        // 4. Chats: /api/projects/:pid/chats
        if (parts[1] === 'chats') {
          if (method === 'GET') {
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(projectChats[pid] || []),
            })
          }
          if (method === 'POST') {
            let bodyData: any = {}
            try {
              bodyData = req.postDataJSON()
            } catch {
              /* ignore */
            }
            const newChat = {
              id: `chat-${Date.now()}`,
              project_id: pid,
              title: bodyData?.first_message || 'Nova conversa',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
            }
            if (!projectChats[pid]) projectChats[pid] = []
            projectChats[pid].unshift(newChat)
            return route.fulfill({
              status: 201,
              contentType: 'application/json',
              body: JSON.stringify(newChat),
            })
          }
        }

        // 5. Project single item: /api/projects/:pid
        if (parts.length === 1) {
          const proj = projects.find((p) => p.id === pid)
          if (method === 'DELETE') {
            projects = projects.filter((p) => p.id !== pid)
            delete projectFiles[pid]
            delete projectChats[pid]
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify({ ok: true }),
            })
          }
          if (method === 'PATCH') {
            let bodyData: any = {}
            try {
              bodyData = req.postDataJSON()
            } catch {
              /* ignore */
            }
            if (proj) {
              Object.assign(proj, bodyData)
              if (bodyData.instructions !== undefined) {
                const instrTokens = Math.round((proj.instructions?.length || 0) / 4)
                proj.capacity.breakdown.instructions_tokens = instrTokens
                proj.capacity.total_tokens =
                  instrTokens +
                  proj.capacity.breakdown.memory_tokens +
                  proj.capacity.breakdown.files_tokens
                proj.capacity.usage_percent = Math.min(
                  100,
                  Math.round((proj.capacity.total_tokens / proj.capacity.capacity_limit) * 100)
                )
              }
            }
            return route.fulfill({
              status: 200,
              contentType: 'application/json',
              body: JSON.stringify(proj),
            })
          }
          // GET
          if (!proj) return route.fulfill({ status: 404, body: 'Not found' })
          return route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
              ...proj,
              file_count: (projectFiles[pid] || []).length,
            }),
          })
        }
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(projects),
        })
      }

      // Chat send & prompt validation interceptor
      if (url.includes('/api/chat') || url.includes('/api/run')) {
        try {
          lastPromptPayload = req.postDataJSON()
        } catch {
          /* ignore */
        }
        return route.fulfill({
          status: 200,
          contentType: 'text/event-stream',
          body: 'data: {"type":"chunk","content":"Com base nas diretrizes do projeto e no manual de motores..."}\n\ndata: {"type":"done"}\n\n',
        })
      }

      // Neutral fallback for any other APIs
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })
  })

  test('Ciclo Completo: Visualização, Detalhe, Card Unificado, Capacidade e Isolamento', async ({
    page,
  }) => {
    page.on('console', (msg) => console.log('BROWSER LOG:', msg.type(), msg.text()))
    page.on('pageerror', (err) => console.log('BROWSER ERROR:', err.message))

    // 1. Acessa tela de Projetos
    await page.goto(`${BASE}/?project=proj-esp32`)
    await page.waitForTimeout(1000)
    const onboardingBtn = page.locator('button:has-text("Entendi")')
    if (await onboardingBtn.isVisible().catch(() => false)) {
      await onboardingBtn.click().catch(() => {})
      await page.waitForTimeout(300)
    }

    const html = await page.evaluate(() => document.body.innerHTML)
    console.log('HTML BODY LENGTH:', html.length, 'HTML SNIPPET:', html.slice(0, 300))

    // Captura screenshot do detalhe do projeto
    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '02-projeto-detalhe-header.png'),
    })

    // Valida Breadcrumb no topo
    const breadcrumb = page.locator('.claude-breadcrumb')
    await expect(breadcrumb).toBeVisible()
    await expect(breadcrumb).toContainText(/Projetos|Projects/)
    await expect(breadcrumb).toContainText('Projeto Robô ESP32')

    // Valida Descrição editável
    const desc = page.locator('.claude-detail-desc')
    await expect(desc).toBeVisible()
    await expect(desc).toContainText('Firmware, pinout e controle')

    // 2. Card Unificado da Direita: 3 Seções contínuas
    const sideCard = page.locator('.claude-unified-side-card')
    await expect(sideCard).toBeVisible()

    // Seção 1: Instruções
    const instrSection = page.locator('.claude-section-instructions')
    await expect(instrSection).toBeVisible()
    await expect(instrSection.locator('h3')).toContainText(/Instruções|Instructions/)
    await expect(page.locator('.claude-instructions-preview')).toContainText('ESP-IDF e C++')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '03-instrucoes-preview.png'),
    })

    // Seção 2: Memória
    const memSection = page.locator('.claude-section-memory')
    await expect(memSection).toBeVisible()
    await expect(memSection.locator('h3')).toContainText(/Memória|Memory/)
    await expect(memSection.locator('.claude-scope-badge')).toContainText(/Apenas você|Only you/)
    await expect(memSection.locator('.claude-link-btn')).toContainText(/Ver memória|View memory/)

    // Seção 3: Contexto
    const ctxSection = page.locator('.claude-section-context')
    await expect(ctxSection).toBeVisible()
    await expect(ctxSection.locator('h3')).toContainText(/Contexto|Context/)

    // 3. Barra de Capacidade de Contexto
    const capacityBox = page.locator('.claude-capacity-box')
    await expect(capacityBox).toBeVisible()
    await expect(page.locator('.claude-capacity-bar-track')).toBeVisible()
    await expect(page.locator('.claude-capacity-bar-fill')).toBeVisible()

    // Hover/focus no ícone info para validar o popup de breakdown
    const infoTrigger = page.locator('.claude-capacity-tooltip-trigger')
    await infoTrigger.focus()
    await infoTrigger.hover().catch(() => {})
    const tooltip = page.locator('.claude-capacity-tooltip-popup')
    await expect(tooltip).toBeVisible()
    await expect(tooltip).toContainText('Capacidade de Contexto do Projeto')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '05-barra-capacidade.png'),
    })

    // 4. Grid de Contexto e Badges de Extensão
    // Injeta 2 arquivos fictícios no estado do projeto
    projectFiles['proj-esp32'] = [
      {
        id: 'file-1',
        project_id: 'proj-esp32',
        filename: 'manual_motores.md',
        file_size: 2840,
        token_count: 710,
        index_status: 'ready',
        created_at: new Date().toISOString(),
      },
      {
        id: 'file-2',
        project_id: 'proj-esp32',
        filename: 'pinout_esp32.pdf',
        file_size: 15400,
        token_count: 3850,
        index_status: 'ready',
        created_at: new Date().toISOString(),
      },
    ]

    // Recarrega o projeto para renderizar o grid
    await page.goto(`${BASE}/?project=proj-esp32`)
    await page.waitForTimeout(600)

    const contextGrid = page.locator('.claude-context-grid')
    await expect(contextGrid).toBeVisible()
    const cards = page.locator('.claude-context-card')
    await expect(cards).toHaveCount(2)

    // Valida primeiro card: nome, tamanho e badge
    await expect(cards.nth(0)).toContainText('manual_motores.md')
    await expect(cards.nth(0)).toContainText(/2[.,]8\s*kB/)
    await expect(cards.nth(0).locator('.context-ext-badge')).toContainText('MD')

    // Valida segundo card: nome e badge PDF
    await expect(cards.nth(1)).toContainText('pinout_esp32.pdf')
    await expect(cards.nth(1).locator('.context-ext-badge')).toContainText('PDF')

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '04-contexto-grid-2colunas.png'),
    })

    // 5. Teste de Busca em Tempo Real no Contexto (🔍)
    const searchBtn = page.locator('.context-head-actions button').first()
    await searchBtn.click()
    const searchInput = page.locator('.claude-context-search-row input')
    await expect(searchInput).toBeVisible()

    // Filtra por "pinout"
    await searchInput.fill('pinout')
    await expect(page.locator('.claude-context-card')).toHaveCount(1)
    await expect(page.locator('.claude-context-card')).toContainText('pinout_esp32.pdf')

    // Limpa busca
    await searchInput.fill('')
    await expect(page.locator('.claude-context-card')).toHaveCount(2)

    // 6. Teste de Modal de Memória e "Sintetizar agora"
    await page.locator('.claude-link-btn').click()
    const memoryModal = page.locator('.claude-memory-modal')
    await expect(memoryModal).toBeVisible()
    await expect(memoryModal).toContainText(/Memória do Projeto|Project Memory/)

    const synthBtn = page.locator('.claude-btn-synthesize')
    await expect(synthBtn).toBeVisible()
    await synthBtn.click()
    await page.waitForTimeout(500)

    // Valida que o texto sintetizado preencheu o editor
    const memoryEditor = page.locator('.claude-memory-editor textarea')
    await expect(memoryEditor).toHaveValue(/Fatos consolidados do projeto/)

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '06-modal-memoria-sintese.png'),
    })

    // Fecha o modal
    await page.locator('.claude-memory-modal-footer .claude-btn-primary').click()
    await expect(memoryModal).not.toBeVisible()

    // 7. Lista "Recentes" em Linha Única
    const recentsHeader = page.locator('.claude-recents-header')
    await expect(recentsHeader).toBeVisible()
    await expect(recentsHeader).toContainText(/Recentes|Recent/)

    const chatRow = page.locator('.claude-chat-single-row').first()
    await expect(chatRow).toBeVisible()
    await expect(chatRow.locator('.claude-chat-title')).toContainText('Configuração dos pinos PWM')

    // 8. Composer com Botão de Voz e Seletores
    const composer = page.locator('.claude-composer')
    await expect(composer).toBeVisible()
    await expect(page.locator('.claude-composer-mic-btn')).toBeVisible()

    // 9. Teste de Isolamento Total com Projeto B
    // Cria Projeto B vazio
    projects.push({
      id: 'proj-b',
      name: 'Projeto B Isolado',
      description: 'Projeto limpo para teste de isolamento estrito',
      instructions: '',
      is_favorite: 0,
      memory: null,
      file_count: 0,
      updated_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      capacity: {
        total_tokens: 0,
        capacity_limit: 131072,
        usage_percent: 0,
        mode: 'full',
        breakdown: { instructions_tokens: 0, memory_tokens: 0, files_tokens: 0, file_count: 0 },
      },
    })

    // Navega para o Projeto B
    await page.goto(`${BASE}/?project=proj-b`)
    await page.waitForTimeout(600)

    // Valida nome do Projeto B no breadcrumb
    await expect(page.locator('.claude-breadcrumb-current')).toContainText('Projeto B Isolado')

    // Valida que NÃO há instruções do Projeto A
    await expect(page.locator('.claude-instructions-preview')).toContainText(
      /Adicionar instruções|Add instructions/
    )

    // Valida que NÃO há arquivos do Projeto A
    await expect(page.locator('.claude-files-empty')).toBeVisible()
    await expect(page.locator('.claude-context-card')).toHaveCount(0)

    // Valida que NÃO há memória do Projeto A
    await expect(page.locator('.claude-memory-preview')).toContainText(
      /Nenhuma memória sintetizada|No memory synthesized/
    )

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '07-isolamento-projeto-b.png'),
    })

    // 10. Volta para a lista de projetos e valida renderização
    await page.locator('.claude-breadcrumb-link').click()
    await page.waitForTimeout(500)
    await expect(page.locator('.claude-projects-grid')).toBeVisible()
    await expect(page.locator('.claude-project-card')).toHaveCount(2)

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '01-projetos-lista.png'),
    })
  })

  test('Layout Responsivo Mobile (375x667)', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto(`${BASE}/?project=proj-esp32`)
    await page.waitForTimeout(800)

    // Confirma que não há overflow horizontal no documento
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth)
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth)
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 2)

    await page.screenshot({
      path: path.join(SCREENSHOTS_DIR, '08-responsivo-mobile.png'),
    })
  })

  test('Ações do Composer (+) e Inspeção de Documentos do Contexto', async ({ page }) => {
    // Adiciona um arquivo mock ao proj-esp32
    projectFiles['proj-esp32'] = [
      {
        id: 'file-doc-01',
        project_id: 'proj-esp32',
        filename: 'manual_motores.pdf',
        file_size: 15400,
        token_count: 850,
        index_status: 'ready',
        created_at: new Date().toISOString(),
        extracted_text: '# Manual de Motores ESP32\n\nEspecificações de corrente: 1.2A máximo.',
      },
    ]

    await page.goto(`${BASE}/?project=proj-esp32`)
    await page.waitForTimeout(600)

    // 1. Valida que o seletor de provedor NÃO está duplicado (apenas ModelSelector está presente)
    await expect(page.locator('.claude-composer-selectors .provider-selector')).toHaveCount(0)
    await expect(page.locator('.claude-composer-selectors .model-selector, .claude-composer-selectors .simple-mode-container')).toHaveCount(1)

    // 2. Valida o botão "+" do composer abrindo o menu de ações PlusActionMenu
    const plusBtn = page.locator('.claude-composer .composer-plus-btn')
    await expect(plusBtn).toBeVisible()
    await plusBtn.click()

    const plusMenu = page.locator('.plus-menu-popover, .composer-tools-sheet')
    await expect(plusMenu).toBeVisible()
    await expect(plusMenu).toContainText(/Adicionar arquivos ou fotos|Add files/)
    await expect(plusMenu).toContainText(/Melhorar prompt|Enhance/)
    await expect(plusMenu).toContainText(/Busca na web|Web search/)

    // Fecha o menu de ações
    await page.keyboard.press('Escape')
    await page.waitForTimeout(300)

    // 3. Valida a inspeção e abertura de documentos anexados ao clicar no card de contexto
    const fileCard = page.locator('.claude-context-card').first()
    await expect(fileCard).toBeVisible()
    await expect(fileCard).toContainText('manual_motores.pdf')

    // Clica no card para abrir o modal de inspeção
    await fileCard.click()

    const fileModal = page.locator('.claude-file-modal')
    await expect(fileModal).toBeVisible()
    await expect(fileModal.locator('.claude-file-modal-title')).toHaveText('manual_motores.pdf')
    await expect(fileModal.locator('.claude-file-text-content')).toContainText('Manual de Motores ESP32')
    await expect(fileModal.locator('a', { hasText: /Abrir original|Open original/ })).toBeVisible()
    await expect(fileModal.locator('a', { hasText: /Baixar|Download/ })).toBeVisible()

    // Fecha o modal
    await fileModal.locator('.claude-icon-btn').click()
    await expect(fileModal).not.toBeVisible()
  })
})
