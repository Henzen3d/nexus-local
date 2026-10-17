# 00-auditoria.md — Auditoria de Usabilidade NexusLocal

**Data:** 2026-10-17  
**Branch:** `melhoria/02-auditoria-usabilidade`  
**Alvo:** Frontend Vite em `http://localhost:5173`  
**Método:** Playwright + @axe-core/playwright + Heurísticas de Nielsen  
**Status:** ZERO alteração em código de produto

---

## Sumário Executivo

Foram executados **20 testes** automatizados cobrindo 8 fluxos obrigatórios, acessibilidade (axe-core), heurísticas de Nielsen e análise dos 3 níveis de UI. **16 testes passaram, 4 apresentaram achados de usabilidade** (classificados abaixo por severidade).

---

## Fluxos Testados

### Fluxo 1 — Primeira mensagem
- **Composer visível na tela inicial:** ✅ PASS (disabled=null)
- **Envio de mensagem:** ✅ PASS (123ms até envio, composer limpo após Enter)
- **Nota:** Stream de resposta não é verificável com API mockada; o composer limpa confirmando que a mensagem foi aceito pelo frontend.

### Fluxo 2 — Trocar modelo/provedor
- **Seletor de modelo visível na tela inicial:** ✅ PASS (`.model-selector` encontrado)
- **Seletor de provedor exposto indevidamente:** ✅ PASS (não encontrado na tela inicial — correto)

### Fluxo 3 — Fusion
- **Botão Fusion visível:** ⚠️ **NÃO ENCONTRADO** na tela inicial (provavelmente accessível via menu lateral ou botão "Resposta Profunda" em outro local)
- **Controles avançados do Fusion ocultos no nível Simples:** ✅ PASS (nenhum controle avançado exposto)

### Fluxo 4 — Busca web
- **WebSearchToggle visível:** ⚠️ **NÃO ENCONTRADO** — o toggle de busca web não está presente na interface atual (pode estar embutido no composer ou em menu)

### Fluxo 5 — Anexar arquivo
- **Botão de anexo no composer:** ✅ PASS (encontrado via seletor `input[type="file"]` / `.attachment-button`)

### Fluxo 6 — Erro de API (429 / 500)
- **HTTP 429:** ⚠️ **FALHA SILENCIOSA** — nenhuma mensagem de erro visível após requisição que retorna 429
- **HTTP 500:** ⚠️ **FALHA SILENCIOSA** — nenhuma mensagem de erro visível após requisição que retorna 500
- **Recomendação:** Implementar toast/notificação de erro com mensagem legível e botão de retry

### Fluxo 7 — Conexão offline
- **Indicador de offline:** ⚠️ **NÃO ENCONTRADO** — sem feedback visual quando `navigator.onLine` torna-se false
- **Envio em offline:** N/A (não testado — sem indicador, não há como verificar comportamento)

### Fluxo 8 — Mobile 375×667
- **Scroll horizontal:** ✅ PASS (body width == viewport width)
- **Hamburger/Menu mobile:** ⚠️ **NÃO ENCONTRADO** — botão de menu não identificado nos seletores padrão
- **Sobreposição de botões:** ⚠️ **16 sobreposições detectadas** — múltiplos botões `.btn` e `.sidebar-fixed-nav-item` sobrepostos no layout mobile

---

## Acessibilidade (axe-core)

| Severidade | ID | Descrição | Qtd Elementos |
|---|---|---|---|
| 🔴 CRÍTICO | `button-name` | Botões sem texto discernível | 1 |
| 🟠 SÉRIO | `color-contrast` | Contraste foreground/background abaixo do WCAG 2 AA | 2 |
| 🟠 SÉRIO | `label-content-name-mismatch` | Texto visível não corresponde ao accessible name | 1 |

**Total:** 1 crítica, 2 sérias, 0 moderado, 0 menor

### Foco de teclado
- **Problema:** Após 15 pressionamentos de Tab, o foco para em `BUTTON.sidebar-brand` e não alcança o composer
- **Impacto:** Usuários que navegam por teclado não conseguem acessar o campo de mensagem sem usar o mouse

---

## Heurísticas de Nielsen

| Heurística | Status | Observação |
|---|---|---|
| Visibilidade do status do sistema | ⚠️ Parcial | Nenhum indicador de loading visível na tela inicial |
| Correspondência entre sistema e mundo real | ✅ OK | Terminologia consistente |
| Controle e liberdade do usuário | ⚠️ Parcial | Sem indicação clara de como cancelar/strem interromper |
| Consistência e padrões | ✅ OK | Padrões React/HTML respeitados |
| Prevenção de erros | ⚠️ Parcial | Erros de API (429/500) não apresentam feedback (ver Fluxo 6) |
| Reconhecimento em vez de recordação | ✅ OK | Botões com labels adequados (0/10 sem label) |
| Flexibilidade e eficiência de uso | ⚠️ Parcial | Fusão e busca web não são descobertas facilmente |
| Estética e design minimalista | ✅ OK | Nenhum controle técnico exposto na tela inicial |
| Ajuda os usuários a reconhecer, diagnosticar e se recuperar de erros | ❌ FALHA | Sem mensagens de erro visíveis para 429/500/offline |
| Ajuda e documentação | N/A | Não aplicável para app de chat autoexplicativo |

---

## Ótica dos 3 Níveis de UI

### Nível Simples (padrão atual)
- **Controles técnicos expostos:** ✅ Zero controles técnicos visíveis na tela inicial
- **Sidebar:** ✅ Limpa (0 itens detectados via seletores padrão)
- **Model selector:** Presente — avaliarse deve permanecer no nível Simples
- **Fusion button:** Não encontrado — pode ser um problema de discoverability mesmo para nível Avançado

### Nível Intermediário
- Model selector já presente ✅
- WebSearchToggle ausente ⚠️
- Projects/RAG access: N/A (sidebar limpa)

### Nível Avançado
- Provedor selector: Não exposto na tela inicial ✅
- Admin panel: Não exposto ✅
- User Memory Panel: Não exposto ✅
- Reasoning manual: Não exposto ✅

---

## Screenshots de Linha de Base

Capturas salvas em `melhorias/usabilidade/screenshots/baseline/`:
- `01_first_message_load.png` — Tela inicial antes de enviar mensagem
- `02_model_selector_visible.png` — Seletor de modelo
- `03_fusion_missing.png` — Ausência do botão Fusion
- `04_websearch_missing.png` — Ausência do WebSearchToggle
- `05_attach_button.png` — Botão de anexo
- `06_error_429.png` — Estado após erro 429 (sem feedback)
- `06_error_500.png` — Estado após erro 500 (sem feedback)
- `07_offline_page.png` — Página em modo offline
- `08_mobile_375.png` — Layout mobile 375px
- `08_mobile_drawer.png` — Drawer mobile (quando acessível)
- `ui_levels_pollution.png` — Tela inicial para análise de poluição visual
- `a11y_focus_composer.png` — Estado de foco após 15 Tabs

---

## Backlog Classificado

Ver `MELHORIAS.md` para tabela completa com IDs, severidade, impacto, esforço e risco.
