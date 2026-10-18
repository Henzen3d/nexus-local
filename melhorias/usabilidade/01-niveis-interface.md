# Especificação: 3 Níveis de Interface (Iteração 4)

## Objetivo
Implementar um sistema de níveis de interface (`ui_level`) que permite ao usuário controlar o grau de complexidade visual da aplicação, do mais simples ao mais avançado.

## Requisitos

### 1. Estado `ui_level` no store
- Tipo: `'simple' | 'intermediate' | 'advanced'`
- Padrão inicial: `'simple'`
- Persistência: `localStorage` com chave `nexuslocal_ui_level`
- Acessível via `useStore`:
  - `uiLevel: 'simple' | 'intermediate' | 'advanced'`
  - `setUiLevel(level: string): void`

### 2. Seletor de Nível na UI
- Posicionado na sidebar (header), forma limpa sem poluir o composer
- Opções: `Simples | Intermediário | Avançado`
- Em 375px de largura, não deve gerar sobreposição com outros elementos

### 3. Comportamento por Nível

#### Simples (`simple`)
- Composer enxuto atual com gaveta `+` ("Ações e ferramentas")
- Oculta seletores manuais de modelo/provedor
- Oculta configurações avançadas
- Força: `smart_router = true`, `reasoning_effort_auto = true`

#### Intermediário (`intermediate`)
- Exibe seletor compacto de modelo (`ModelSelector`)
- Acesso a Projetos/RAG na sidebar
- Mantém gaveta `+` funcional

#### Avançado (`advanced`)
- Libera todos os controles técnicos:
  - Seletor de provedor
  - Reasoning manual
  - Configurações completas de Fusion/Judge
  - `UserMemoryPanel`
  - `AdminPanel`
  - Badges `was_fallback`

### 4. Testes
- Playwright: alternância entre os 3 níveis
- Playwright: persistência via localStorage
- Playwright: comportamento correto de cada nível (elementos visíveis/ocultos)

## Implantação
1. Criar componente `UiLevelSelector` em `frontend/src/components/ui/`
2. Adicionar ao sidebar/header
3. Adicionar estado e acciones ao `useStore.ts`
4. Criar testes em `melhorias/usabilidade/ui-levels.spec.ts`
5. Capturar screenshots em `melhorias/usabilidade/screenshots/depois/`
