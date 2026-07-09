# Plano: Internacionalização (i18n) do NexusLocal

## Context

A aplicação NexusLocal (React + Vite + Zustand) está **inteiramente em Português (Brasil)**: strings hardcoded em ~30 componentes, store, hooks e toasts. Não existe biblioteca de i18n nem seletor de idioma.

O objetivo é oferecer a interface nos **8 idiomas** abaixo, com **pt-BR como idioma de origem/padrão**, seletor nas configurações e persistência da preferência.

| Código BCP 47 | Idioma |
|---|---|
| `pt-BR` | Português (Brasil) — padrão / fonte |
| `en-US` | English (United States) |
| `fr-FR` | Français (France) |
| `de-DE` | Deutsch (Deutschland) |
| `ja` | 日本語 (日本) |
| `ko` | 한국어 (대한민국) |
| `es-419` | Español (Latinoamérica) |
| `es-ES` | Español (España) |

**Fora do escopo desta entrega (follow-up opcional):**
- Mensagens de erro do backend FastAPI (ainda em PT; a UI pode exibir o `detail` bruto da API).
- Conteúdo gerado por LLMs (respostas do chat), títulos de conversas salvos, nomes de providers/modelos.
- Tradução de docs/`README.md` e arquivos estáticos legados (`NexusLocal.html`).

---

## Abordagem recomendada

### Stack
- **`i18next` + `react-i18next`** — padrão de mercado no React, suporte a interpolação, pluralização e troca de idioma em runtime.
- Arquivos JSON por locale em `frontend/src/i18n/locales/`. Importação estática recomendada para latência zero nas mudanças de idioma.
- Preferência de idioma em **Zustand + `localStorage`** (`nexuslocal_locale`), no mesmo padrão de `theme` / `chatFont`.
- Fallback de detecção inteligente: `localStorage` → `navigator.language` (mapeado para subcódigos, ex: `es-*` → `es-419`) → `pt-BR`.

### Estrutura de chaves (namespaces lógicos em um JSON aninhado)

```
common.*          // Fechar, Salvar, Cancelar, Erro, Carregar…
auth.*            // Login / cadastro
chat.*            // Saudação, chips, input, fusion toggle
sidebar.*         // Navegação, conversas, logout
conversations.*   // Lista / busca / filtros
artifacts.*       // Painel e lista de artefatos
settings.*        // AdminPanel (Geral, Aparência, Idioma…)
providers.*       // Providers, modelos, sync
tools.*           // Enhancer, Fusion, Web Search, Vision, Cache…
admin.*           // Usuários, rankings, dashboard
errors.*          // Toasts e mensagens de falha no client
pwa.*             // Instalar app, permissões
```

Exemplo de uso nos componentes:

```tsx
const { t } = useTranslation()
// ...
<title>{t('chat.openSidebar')}</title>
{t('chat.greeting.morning')}, <strong>{displayName}</strong>
```

Interpolação: `t('chat.searchingWeb', { query })`.

### Seletor de idioma (UI)
- Em **Configurações → Aparência & Preferências** (mobile bottom-sheet / desktop general), ao lado de tema e fonte.
- Lista com **nome nativo** de cada idioma (ex.: `日本語`, `Español (Latinoamérica)`).
- Ao trocar: `i18n.changeLanguage(code)`, `setLocale(code)`, atualizar `document.documentElement.lang`.

### Boas Práticas de Robustez
1. **Mapeamento do Fallback do Navegador**: Usar uma função utilitária para mapear variações regionais do navegador (`es-MX`, `es-AR` etc.) para os locales suportados pelo app, preferindo `es-419` para LatAm e `es-ES` para Espanha.
2. **i18next Type-Safety**: Criar arquivo `d.ts` para tipagem estrita de chaves de strings baseada no `pt-BR.json`, evitando erros de digitação em tempo de desenvolvimento.
3. **Formatação de Dados Localizada**: Utilizar a API nativa `Intl` do JavaScript (como `Intl.DateTimeFormat` e `Intl.NumberFormat`) que respondem automaticamente ao locale ativo, evitando dependências extras para formatar datas do chat e contadores numéricos do Admin Panel.
4. **Padrão de Pluralização (i18next v21+)**: Seguir o padrão de sufixos `_one` e `_other` no JSON para pluralização.

### Fontes CJK
- Manter stack atual (Inter / system). Navegadores já caem para fontes do sistema em japonês/coreano; sem mudança obrigatória de CSS nesta fase.

---

## Arquivos críticos

### Novos
| Arquivo | Função |
|---|---|
| `frontend/src/i18n/index.ts` | Init i18next, detecção, export `SUPPORTED_LOCALES` |
| `frontend/src/types/i18next.d.ts` | Definições de tipagem estrita para o i18next com base no pt-BR.json |
| `frontend/src/i18n/locales/pt-BR.json` | Catálogo-fonte (todas as chaves) |
| `frontend/src/i18n/locales/en-US.json` | Tradução |
| `frontend/src/i18n/locales/fr-FR.json` | Tradução |
| `frontend/src/i18n/locales/de-DE.json` | Tradução |
| `frontend/src/i18n/locales/ja.json` | Tradução |
| `frontend/src/i18n/locales/ko.json` | Tradução |
| `frontend/src/i18n/locales/es-419.json` | Tradução (LatAm) |
| `frontend/src/i18n/locales/es-ES.json` | Tradução (Espanha) |

### Modificados (infra)
| Arquivo | Mudança |
|---|---|
| `frontend/package.json` | deps `i18next`, `react-i18next` |
| `frontend/src/main.tsx` | `import './i18n'` + `I18nextProvider` se necessário |
| `frontend/src/store/useStore.ts` | `locale`, `setLocale` (com `i18n.changeLanguage` e `document.documentElement.lang`), persistência `nexuslocal_locale` |
| `frontend/index.html` | `lang` inicial; runtime atualiza via JS |
| `frontend/src/App.tsx` | sync `document.documentElement.lang` + strings do Toast |

### Modificados (extração de strings — por prioridade)
1. **Auth / shell:** `Login.tsx`, `App.tsx`, `Sidebar.tsx`, `InstallPWAButton.tsx`
2. **Chat:** `ChatWindow.tsx`, `MessageInput.tsx`, `MessageBubble.tsx`, `ModelSelector.tsx`, `ProviderSelector.tsx`, `FusionStatusCard.tsx`, `WebSearchToggle.tsx`, `AttachmentButton.tsx`, `AttachmentChip.tsx`, `AIMetadataDisplay.tsx`, `AIStatusIndicator.tsx`
3. **Listas:** `ConversationsPanel.tsx`, `ArtifactsPanel.tsx`, `ArtifactPanel.tsx`
4. **Settings (maior volume):** `AdminPanel.tsx` (~2k linhas), `CachePanel.tsx`, `EnhancerSettings.tsx`, `FusionSettings.tsx`, `WebSearchSettings.tsx`, `VisionRelaySettings.tsx`, `FreeRegistrySettings.tsx`, `FamilySettings.tsx`, `RankingWeightsSettings.tsx`, `RankingsView.tsx`, `UsageDashboard.tsx`, `RankBadge.tsx`
5. **Hooks / store toasts:** `hooks/useChat.ts`, trechos de `useStore.ts` com textos de usuário (`'Usuário'`, toasts se houver)

### Reuso existente
- Padrão de preferências em `useStore.ts` (`setTheme` / `localStorage.setItem('nexuslocal_theme', …)`).
- UI de bottom-sheets de tema/fonte em `AdminPanel.tsx` — copiar o mesmo padrão para o sheet de idioma.
- Toasts via `showToast(message, type)` — passar sempre `t('…')` no call site.

---

## Fases de implementação

### Fase 1 — Infraestrutura
1. Instalar `i18next` e `react-i18next`.
2. Criar `i18n/index.ts` com os 8 locales, fallback `pt-BR`.
3. Adicionar `locale` / `setLocale` no Zustand.
4. Importar i18n em `main.tsx`.
5. Criar `pt-BR.json` completo (catálogo-fonte) a partir de varredura dos componentes.
6. UI do seletor de idioma (mobile + desktop) em `AdminPanel`.

### Fase 2 — Wiring dos componentes
Substituir strings literais por `t('chave')` / `t('chave', { var })` em todos os componentes listados. Manter nomes de marca (`NexusLocal`, `Fusion`, providers) sem traduzir quando forem product names.

### Fase 3 — Traduções
Partindo de `pt-BR.json`, gerar os outros 7 JSONs com:
- Vocabulário técnico consistente (model, provider, cache, ranking…).
- `es-419` vs `es-ES` diferenciados onde importa (ex.: *computadora/ordenador*, *archivo/fichero*, *celular/móvil*).
- Placeholders preservados (`{{query}}`, `{{count}}`).

### Fase 4 — Polimento
- Atualizar `document.documentElement.lang` e `meta description` se aplicável.
- Garantir que `aria-label`, `title`, `placeholder` e `confirm()`/`alert()` também usem `t()`.
- Chips de welcome e saudações (`Bom dia` / `Boa tarde` / `Boa noite`) com chaves por período do dia.
- Datas/números: onde houver formatação, usar `Intl` com o locale ativo (se já existir formatação de data na UI).

---

## Convenções de implementação

1. **Nunca** deixar string de UI hardcoded em PT após a migração (exceto logs de debug `console.*`).
2. Chaves em **camelCase** e agrupadas por feature (`settings.appearance.colorMode`).
3. `pt-BR.json` é a **fonte da verdade** de chaves; outros locales devem ter o mesmo conjunto de chaves.
4. Preferir `useTranslation()` em componentes; em store/funções fora de React, usar `i18n.t()` importado de `./i18n`.
5. Erros da API: na Fase 1–3, mapear apenas erros **conhecidos do client** (validação local, toasts gerados no front). Detalhes HTTP do backend permanecem no idioma original até um follow-up.

---

## Verification

1. **Build:** `cd frontend && npm run build` sem erros de TypeScript.
2. **Troca de idioma:** em Configurações, selecionar cada um dos 8 idiomas e confirmar:
   - Login, sidebar, chat vazio (saudação + chips), settings shell, painel de artefatos.
3. **Persistência:** recarregar a página → locale permanece.
4. **Detecção:** limpar `nexuslocal_locale` e validar fallback para browser / pt-BR.
5. **Smoke visual:** japonês e coreano legíveis; layout não quebra em labels longos (DE/FR).
6. **Regressão:** login, envio de mensagem, abrir settings, trocar tema ainda funcionam com locale ≠ pt-BR.

---

## Estimativa de esforço (orientação)

| Área | Complexidade |
|---|---|
| Infra + seletor | Baixa |
| Extração AdminPanel + settings tools | Alta (maior volume) |
| Restante UI | Média |
| 7 traduções completas | Alta (volume de chaves) |

Entrega única recomendada: infra + catálogo pt-BR + wiring completo + 7 locales, para o seletor não mostrar idiomas “metade traduzidos”.
