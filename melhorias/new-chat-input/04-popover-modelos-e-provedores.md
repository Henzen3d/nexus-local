# 🎯 04 - Novo Balão Unificado de Modelos & Provedores
**Multi+ (NexusLocal) — Consolidação no Popover de Seleção com Toggle**

Este documento detalha a reestruturação da seleção de IAs no Multi+, integrando o **Toggle de Auto-Roteamento Inteligente (Smart Router)**, o **Filtro de Provedores** e a **Lista de Modelos Reais** dentro de um único balão popover ancorado no rodapé.

---

## 🧭 O Problema da Separação Atual

Hoje, o fluxo do usuário é fragmentado em dois extremos opostos da interface:
1. O usuário precisa olhar para o topo da tela (`chat-header-left`) para escolher o Provedor (`ProviderSelector`).
2. Depois precisa olhar para o canto inferior direito (`input-actions-right`) para escolher o Modelo (`ModelSelector`).
3. O topo da lista de modelos exibe uma opção manual de *"Auto (Roteamento Inteligente)"*, disputando espaço na mesma listagem com centenas de modelos específicos.

---

## 💡 A Nova Estrutura Unificada do Balão

Ao clicar no pill de modelo localizado no rodapé do chat (`[ 🎯 Auto ]` ou `[ Modelo Ativo ▾ ]`), abre-se um balão suspenso com **três camadas funcionais perfeitamente organizadas**:

```
┌────────────────────────────────────────────────────────────────────────┐
│ [ Balão Unificado de Modelos & Provedores ]                            │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ CAMADA 1: Auto-Roteamento Inteligente ────────────────────────────┐ │
│ │  🎯 Roteamento Inteligente                 [ Toggle Switch: ON ]   │ │
│ │     Seleciona a melhor IA por contexto, cota e velocidade          │ │
│ └────────────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ CAMADA 2: Filtro de Navegação de Provedores (Abas) ───────────────┐ │
│ │  ( [Todos] )  [OpenRouter]  [Anthropic]  [OpenAI]  [Groq]  [Mistral] │ │
│ └────────────────────────────────────────────────────────────────────┘ │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ CAMADA 3: Lista de Modelos Reais do Catálogo ─────────────────────┐ │
│ │  Claude 3.5 Sonnet (Anthropic)                                 [ ✓ ] │ │
│ │  NexusLocal Score: 98.4 · 200k tokens                                │ │
│ │                                                                      │ │
│ │  GPT-4o (OpenAI)                                                     │ │
│ │  NexusLocal Score: 96.2 · 128k tokens                                │ │
│ │                                                                      │ │
│ │  Llama 3.3 70B (Groq)                                                │ │
│ │  NexusLocal Score: 94.0 · Ultra-rápido · 128k tokens                 │ │
│ ├────────────────────────────────────────────────────────────────────┤ │
│ │  Mais modelos                                                    > │ │
│ └────────────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 🎛️ 1. O Toggle Switch de Auto-Roteamento ("Trogle")

### 1.1 Separação entre Auto e Seleção Manual (Resolução [P1])
Para evitar que o usuário perca sua escolha manual ao alternar o modo Auto:
* O estado do componente mantém a referência de `lastManualModelId` e `lastManualProviderId`.
* **Quando o Toggle é Ligado (ON):**
  * Invoca `selectModel('auto', 'auto')`.
  * O pill do rodapé exibe `🎯 Auto (Roteamento)`.
  * A lista de modelos abaixo permanece visível, com uma indicação sutil de que a orquestração dinâmica está ativa.
* **Quando o Toggle é Desligado (OFF):**
  * Restaura imediatamente o par anterior `(lastManualModelId, lastManualProviderId)`.
  * O usuário volta ao modelo que estava utilizando anteriormente sem qualquer atrito.

### 1.2 Especificação Visual do Toggle (Estilo `trogle-conectores.jpg`)
* Adota o padrão de switch documentado na referência:
  * Track arredondado de `40px × 22px` em `var(--surface-cream-strong)`.
  * Quando ativo, track assume azul/primário vibrante (`var(--accent, #6366f1)` ou `var(--primary)`).
  * Thumb circular branco deslizante de `16px` com sombra sutil.

---

## 🏷️ 2. Filtro Horizontal de Provedores (Abas em Pílulas)

### 2.1 Desacoplamento entre Filtro de Navegação e Seleção Efetiva (Resolução [P1])
* O estado `providerFilter` é estritamente um **filtro visual local** do popover:
  * Clicar na aba `Anthropic` apenas filtra quais modelos aparecem na listagem abaixo.
  * **Não altera** o modelo ativo do usuário até que ele clique efetivamente em um item da lista.
* **Pílulas disponíveis:**
  * `Todos` (exibe modelos ativos de todos os provedores cadastrados).
  * Pílulas para cada provedor configurado com modelos habilitados (`OpenRouter`, `Anthropic`, `OpenAI`, `Groq`, etc.).
* Barra com scroll horizontal invisível (`scrollbar-width: none`), com excelente suporte para arrastar e toque mobile.

---

## 📋 3. Lista de Modelos Reais do Multi+

### 3.1 Utilização de Dados Reais do Catálogo
* Em conformidade com o ecossistema Multi+, a lista exibe exclusivamente dados reais do tipo `Model`:
  * `display_name`: Nome real do modelo cadastrado.
  * `provider_name`: Identificador do provedor (exibido quando o filtro estiver em "Todos").
  * `nexuslocal_score`: RankBadge oficial do sistema de benchmark.
  * `context_length`: Capacidade de contexto (ex: `128k`, `200k`).
  * `quota_status`: Alerta visual `AlertCircle` suave caso o modelo esteja com cota esgotada.
* **Sem campos fictícios:** Excluídos campos de "Esforço de raciocínio" ou descrições inventadas, mantendo integridade com a API do backend.

### 3.2 Gaveta *"Mais Modelos >"*
* Se o número de modelos ativos no provedor for superior a 6, os modelos principais com maior pontuação aparecem no topo.
* Os demais modelos são acessíveis através da opção colapsável *"Mais modelos >"*, evitando sobrecarga cognitiva na primeira camada do balão.

---

## 🧹 Limpeza Consequente no Header Superior

Com a absorção completa das decisões de modelo e provedor pelo novo balão:
1. O `ProviderSelector` é **removido do `chat-header-left`** em `ChatWindow.tsx`.
2. O componente `ProviderSelector` continua preservado na base de código para atender à tela de **Projetos** (`ProjectsPanel.tsx`).
3. O cabeçalho do chat fica minimalista, exibindo apenas o toggle da sidebar, o breadcrumb do projeto e informações de título.
