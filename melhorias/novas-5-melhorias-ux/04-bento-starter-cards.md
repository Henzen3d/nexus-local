# 🎯 Frente 04: Bento Cards de Ação Direta no Empty State

## 1. Contexto e Problema Atual

Atualmente no Multi+:
* Na tela inicial sem mensagens abertas (`is-empty`), há um título de boas-vindas com o logo e o nome do usuário, a caixa de prompt centralizada e, no rodapé, quatro chips de texto (*Escrever*, *Aprender*, *Código*, *Brainstorm*).
* Esses chips abrem uma lista vertical em submenu que ocupa espaço e exige múltiplos cliques para o usuário compreender o que a plataforma é capaz de fazer.
* Usuários frequentemente se deparam com a "síndrome da tela em branco", sem explorar as capacidades mais avançadas como o Modo Fusion, processamento de anexos ou pesquisa em tempo real.

## 2. Benchmark de Mercado

* **Manus**: A tela central possui uma composição em Bento Grid com cartões de intenção direta:
  * *Compilar > Sites, aplicativos e jogos*
  * *Criar > Slides, imagens e vídeos*
  * *Começar a partir de um arquivo local*
  * Além de mini-templates com thumbnails em carrossel.
* **Xiaomi MiMo Studio**: Apresenta três cartões editoriais limpos no centro da tela com sugestões práticas e claras (*Quick problem-solving*, *Analyze composition*, *Vision Q&A*).
* **ChatGPT**: Exibe chips horizontais imediatos logo abaixo da caixa de texto (*"Escreva ou edite"*, *"Pesquise na web"*).

---

## 3. Especificação da Solução para o Multi+

Substituir a lista de chips do rodapé por uma seção harmoniosa de **Bento Starter Cards** no centro da tela, posicionada logo abaixo do campo de prompt:

```
                          ┌─────────────────────────────┐
                          │   Multi+  Bom dia, Osmar    │
                          └─────────────────────────────┘

            ┌─────────────────────────────────────────────────────────┐
            │   Como posso ajudar você hoje?                          │
            │   [+] [⚛️ Raciocínio] [🧬 Fusion] [🌐 Web]  [Modelo ▾] [↑]│
            └─────────────────────────────────────────────────────────┘

    ┌───────────────────────────────┐     ┌───────────────────────────────┐
    │ 🧬 Modo Fusion Multi-LLM      │     │ ⚡ Código & Alta Performance   │
    │ Compare a síntese de 3 IAs    │     │ Gere ou refatore com Groq     │
    │ para decisões complexas.      │     │ e Cerebras em latência zero.  │
    └───────────────────────────────┘     └───────────────────────────────┘
    ┌───────────────────────────────┐     ┌───────────────────────────────┐
    │ 📄 Análise de Documentos      │     │ 🌐 Pesquisa Atualizada na Web │
    │ Extraia insights e resuma     │     │ Busque fatos recentes com     │
    │ relatórios de PDFs e CSVs.    │     │ fontes e referências reais.   │
    └───────────────────────────────┘     └───────────────────────────────┘
```

### Características dos Cards
* **Superfície**: Fundo branco no tema claro (`#FFFFFF`) com borda suave (`rgba(0,0,0,0.06)`) e sombra sutil (`0 2px 8px rgba(0,0,0,0.04)`). No tema escuro, superfície carvão aquecida (`#1E1E1E`).
* **Interatividade**: Ao passar o cursor (hover), elevação suave de 2px e realce discreto de borda.
* **Ação em 1 Clique**: Ao clicar no card, ele:
  1. Insere o prompt sugerido no textarea (ou abre o seletor de arquivos, ou liga o modo Fusion).
  2. Foca o cursor para o usuário personalizar ou dar `Enter`.

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 4.1: Componente BentoStarterGrid e BentoCard
- [ ] **4.1.1**: Criar [`BentoStarterGrid.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/BentoStarterGrid.tsx) com layout responsivo (2x2 em telas médias/grandes, 1 coluna em mobile).
- [ ] **4.1.2**: Criar [`BentoCard.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/BentoCard.tsx) com suporte a ícone, título, descrição, tag/badge (ex: `Popular`, `Zero Latência`) e ação `onClick`.
- [ ] **4.1.3**: Micro-animações de entrada (fade-in escalonado de 200ms com delay sutil entre os cards).

### Tarefa 4.2: Integração com Capacidades do Multi+
- [ ] **4.2.1**: Card *Modo Fusion*: ativa o toggle de Fusion no store e pré-preenche o prompt com exemplo de análise comparativa.
- [ ] **4.2.2**: Card *Código*: seleciona um modelo de alta velocidade (ex: Cerebras Llama ou Groq) e insere template de código.
- [ ] **4.2.3**: Card *Análise de Arquivos*: dispara o input de upload de anexos via [`AttachmentButton.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/AttachmentButton.tsx).
- [ ] **4.2.4**: Card *Pesquisa na Web*: ativa o toggle web e insere pergunta factual de exemplo.

### Tarefa 4.3: Transição Fluida para o Início da Conversa
- [ ] **4.3.1**: Ao enviar a primeira mensagem, os cards do Bento Grid realizam fade-out suave e a área de mensagens expande sem travamentos de scroll.
- [ ] **4.3.2**: Garantir que o layout respeite a diretriz de centralização vertical no empty state antes do envio.

### Tarefa 4.4: Personalização e Histórico
- [ ] **4.4.1**: Conectar os cards ao histórico do usuário (se o usuário programa muito, destacar cards de código; se faz análises, destacar cards de síntese).

---

## 5. Critérios de Aceite (Definition of Done)

* [ ] O empty state apresenta visual moderno, sem poluição e alinhado aos padrões do Claude e Manus.
* [ ] O clique em qualquer card executa a ação esperada em menos de 100ms.
* [ ] Em dispositivos móveis (< 640px), o grid se adapta para rolagem horizontal suave ou lista compacta sem quebrar a largura da tela.
