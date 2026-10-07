# 🎯 Frente 01: Composer com Action Pills & Modos Rápidos

## 1. Contexto e Problema Atual

Atualmente no Multi+:
* O seletor de provedor/modelo e o botão de **Modo Fusion** estão localizados no cabeçalho superior (`chat-header`).
* Os botões de anexos, melhorador de prompt e pesquisa web estão no rodapé do input, mas com ícones discretos e sem destaque de estado.
* Isso força o usuário a um padrão de dispersão visual: os olhos estão na caixa de texto na base da tela, mas para trocar modelo ou ativar o Fusion é preciso mover o ponteiro até o topo.

## 2. Benchmark de Mercado

* **DeepSeek**: Implementou pílulas interativas diretamente dentro do rodapé da caixa de prompt:
  * `[ ⚛️ Pensamento Profundo ]` (ativa o raciocínio DeepSeek-R1)
  * `[ 🌐 Pesquisa Inteligente ]` (liga a busca na web)
  * Ambos com estado visual muito claro (borda azul clara e preenchimento suave ao ativar).
* **ChatGPT**: Botão de raciocínio *"Pensar"* integrado inline no input, ao lado do botão de anexos e microfone.
* **Claude**: No rodapé da caixa de texto, integra o seletor compacto de modelo (`Sonnet 3.5 Médio ▾`), botão de anexo e os seletores de contexto (`Chat / Cowork`).

---

## 3. Especificação da Solução para o Multi+

Integrar na barra de rodapé do [`MessageInput.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/MessageInput.tsx) uma faixa unificada de **Action Pills**:

```
┌────────────────────────────────────────────────────────────────────────┐
│  Como posso ajudar você hoje?                                          │
│                                                                        │
│                                                                        │
├────────────────────────────────────────────────────────────────────────┤
│  [+] [ ⚛️ Raciocínio ] [ 🧬 Fusion ] [ 🌐 Web ] [ ✨ Melhorar ]         │
│                                           [ Groq · Llama 3.3 ▾ ] [ ↑ ] │
└────────────────────────────────────────────────────────────────────────┘
```

### Estados Visuais das Pills
1. **Inativo / Default**: Fundo transparente, borda sutil (`var(--border-subtle)`), texto com cor secundária (`var(--text-secondary)`).
2. **Ativo**: Fundo com tom temático suave (ex: Coral/Terracotta suave para Fusion, Azul sutil para Web/Raciocínio, Dourado sutil para Enhancer), borda de destaque e texto em peso 500.
3. **Hover**: Transição suave de fundo (150ms).
4. **Desabilitado**: Opacidade reduzida com tooltip explicativo caso não haja provedor configurado.

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 1.1: Componente Reutilizável de Action Pill
- [ ] **1.1.1**: Criar o componente [`ComposerPill.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/ui/ComposerPill.tsx) com propriedades: `icon`, `label`, `active`, `onClick`, `tooltip`, `disabled`, `variant`.
- [ ] **1.1.2**: Implementar animação suave de micro-transição ao alternar estado ativo/inativo (150ms ease).
- [ ] **1.1.3**: Suporte a atalhos de teclado (ex: `Alt+F` para alternar Fusion, `Alt+W` para Web).

### Tarefa 1.2: Refatoração do Rodapé do Composer
- [ ] **1.2.1**: Em [`MessageInput.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/MessageInput.tsx), reorganizar o container `.input-actions` em duas seções bem definidas: `.input-actions-left` (Pills de Capacidade) e `.input-actions-right` (Seletor de Modelo Compacto + Botão de Envio).
- [ ] **1.2.2**: Adicionar Pill do **Modo Fusion** diretamente no Composer, conectada ao estado do `useStore`.
- [ ] **1.2.3**: Adicionar Pill de **Raciocínio (DeepThink / Thinking)** que alterna para um modelo de raciocínio pré-configurado (ex: DeepSeek R1 ou Gemini Flash Thinking) com 1 clique.
- [ ] **1.2.4**: Atualizar o botão de **Pesquisa Web** para o formato de Pill com indicador textual claro (*Web ativada* / *Web*).
- [ ] **1.2.5**: Integrar a Pill do **Prompt Enhancer** com feedback visual de carregamento durante a melhoria do texto.

### Tarefa 1.3: Seletor de Modelo Compacto Embutido
- [ ] **1.3.1**: Adaptar [`ModelSelector.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/ModelSelector.tsx) para suportar uma variante `compact` apropriada para dentro do input (semelhante ao pill do Claude).
- [ ] **1.3.2**: Exibir badge de velocidade ou custo/tier gratuito ao lado do nome do modelo no popup.
- [ ] **1.3.3**: Manter dropdown com busca rápida e agrupamento por provedor (Groq, Gemini, DeepSeek, Cerebras, OpenRouter).

### Tarefa 1.4: Ajustes de Responsividade Mobile
- [ ] **1.4.1**: Em telas pequenas (< 640px), colapsar as pills menos frequentes em um botão compacto com badge de ferramentas ativas.
- [ ] **1.4.2**: Manter o botão de anexos e o botão de envio acessíveis com área de toque mínima de 44x44px.

### Tarefa 1.5: Design Tokens e Acessibilidade (a11y)
- [ ] **1.5.1**: Definir variáveis semânticas de cores para cada pill ativa em [`index.css`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/index.css).
- [ ] **1.5.2**: Garantir conformidade com WCAG AA para contrastes e foco visível pelo teclado (`aria-pressed`, `aria-label`).

---

## 5. Critérios de Aceite (Definition of Done)

* [ ] O usuário consegue ativar e desativar o Modo Fusion diretamente da barra do input sem olhar para o header.
* [ ] O usuário consegue alternar o modelo ativo diretamente no canto inferior direito do composer.
* [ ] As pílulas ativas apresentam contraste visual nítido nos temas Claro e Escuro.
* [ ] No mobile, a interface não quebra e as pills colapsam elegantemente no BottomSheet existente.
