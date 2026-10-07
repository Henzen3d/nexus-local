# 🎯 Frente 05: Sidebar Modular com Fixados e Agrupamento Temporal

## 1. Contexto e Problema Atual

Atualmente no Multi+:
* A barra lateral ([`Sidebar.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/Sidebar.tsx)) possui mais de 1000 linhas de código e reúne muitas responsabilidades.
* O histórico de conversas tende a crescer em uma lista contínua onde conversas importantes se perdem no scroll.
* A fixação de conversas (favoritas) existe no backend/store, mas não possui uma seção visual de primeiro nível dedicada e destacada com ícones próprios como no Claude, ChatGPT e DeepSeek.

## 2. Benchmark de Mercado

* **Claude**: 
  * Topo limpo e direto: botão de destaque `+ Novo`, atalhos de `Projetos`, `Artifacts`, `</> Código`.
  * Seção nobre e separada de **Fixados** com pequeno marcador e tipografia elegante.
  * Abaixo, seção de **Conversas e tarefas** para o histórico recente.
* **DeepSeek**: 
  * Separação cronológica limpa: *Fixado*, *Hoje*, *Ontem*, *Últimos 7 dias*, *Últimos 30 dias*.
  * Botões de busca e recolhimento integrados ao lado do título.
* **ChatGPT**:
  * Atalhos no topo (*Novo chat*, *Imagens*, *Biblioteca*, *Projetos*), seguidos por *Fixada* e *Recentes*.

---

## 3. Especificação da Solução para o Multi+

```
┌───────────────────────────────────────────────┐
│ [ Multi+ ]                          [◀] [🔍]  │
│                                               │
│ [ + Nova Conversa                          ]  │
│                                               │
│ 📁 Projetos & Contextos                       │
│ ⚡ Artefatos Gerados                          │
│ 🏆 Ranking de Modelos                         │
│ ───────────────────────────────────────────── │
│ FIXADOS                                       │
│ 📌 Arquitetura Multi+ 2026                    │
│ 📌 Ideias de Serviços e APIs                  │
│                                               │
│ HOJE                                          │
│ 💬 Otimização de prompts assíncronos          │
│                                               │
│ ÚLTIMOS 7 DIAS                                │
│ 💬 Configuração de Chaves Groq & Gemini       │
│ 💬 Debugging de WebSocket local               │
│                                               │
│ ───────────────────────────────────────────── │
│ ⚙️ Configurações               👤 Osmar (Free) │
└───────────────────────────────────────────────┘
```

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 5.1: Top Shelf de Acesso Rápido na Sidebar
- [ ] **5.1.1**: Adicionar botão principal com destaque sutil `+ Nova Conversa` no topo da sidebar.
- [ ] **5.1.2**: Adicionar links rápidos diretos com ícones consistentes para:
  * `📁 Projetos` (abre a visão de projetos locais).
  * `⚡ Artefatos` (abre o histórico de códigos e documentos criados).
  * `🏆 Ranking de Modelos` (abre a visão de benchmark de provedores).

### Tarefa 5.2: Seção Nobre de Fixados (Pins)
- [ ] **5.2.1**: Criar bloco visual dedicado `Fixados` no topo da lista de histórico.
- [ ] **5.2.2**: Adicionar botão rápido de pino/estrela visível no hover de cada conversa para fixar/desafixar com 1 clique.
- [ ] **5.2.3**: Permitir colapsar a seção de fixados caso o usuário tenha muitas conversas fixadas.

### Tarefa 5.3: Agrupamento Cronológico Automático
- [ ] **5.3.1**: Agrupar dinamicamente as conversas não-fixadas por:
  * `Hoje`
  * `Ontem`
  * `Últimos 7 dias`
  * `Últimos 30 dias`
  * `Mais antigas`
- [ ] **5.3.2**: Exibir cabeçalhos de data discretos em caixa alta com peso suave (`text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; color: var(--text-tertiary)`).

### Tarefa 5.4: Campo de Busca Rápida na Sidebar
- [ ] **5.4.1**: Adicionar campo de busca rápida retrátil no topo da sidebar (`Ctrl+F` ou ícone de lupa).
- [ ] **5.4.2**: Filtro de título em tempo real com realce do termo pesquisado.

### Tarefa 5.5: Refinamento de Espaçamento e Tipografia
- [ ] **5.5.1**: Ajustar padding interno e respiro entre itens (múltiplos de 8px conforme [`melhorias-UX-UI.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias-UX-UI.md)).
- [ ] **5.5.2**: Garantir hover uniforme e contraste nítido de acordo com as diretrizes do Claude.

---

## 5. Critérios de Aceite (Definition of Done)

* [ ] O usuário consegue fixar e desfixar conversas com um único clique.
* [ ] As conversas fixadas permanecem sempre visíveis no topo da barra.
* [ ] A lista de conversas recentes fica organizada por data sem sobreposição visual.
* [ ] A busca filtra conversas instantaneamente sem delay perceptível.
