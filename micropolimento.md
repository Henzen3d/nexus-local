````markdown
# NexusLocal Chat UX/UI — Fase 5: Microinterações e Polimento Visual

## Objetivo

Após concluir a refatoração estrutural da interface (ThinkingBlock, hierarquia visual, layout e sidebar), esta fase tem como objetivo elevar a percepção de qualidade do produto através de microinterações, consistência visual, animações suaves e preparação para futuras funcionalidades.

O objetivo não é adicionar novos recursos, mas fazer com que toda a interface pareça mais refinada, leve e profissional, aproximando-se da experiência do Claude.ai sem perder a identidade do NexusLocal.

---

# 1. Sistema de Motion Design

## Objetivo

Padronizar todas as animações da aplicação para que transmitam fluidez sem chamar atenção.

### Criar tokens de animação

```css
--motion-fast: 120ms;
--motion-normal: 180ms;
--motion-slow: 220ms;

--ease-standard: ease-out;
```

### Aplicar nos componentes

- Botões
- Sidebar
- ThinkingBlock
- Input
- Dropdowns
- Menus
- Hover
- Tooltips
- Mensagens

### Regras

- Nunca utilizar animações acima de 250ms.
- Evitar animações chamativas.
- Toda transição deve parecer natural.

---

# 2. Streaming da Resposta

## Objetivo

Melhorar a sensação de geração em tempo real durante a resposta da IA.

### Implementar

- Cursor piscando durante o streaming.
- Scroll automático suave.
- Não reposicionar a tela abruptamente.
- Renderização progressiva do Markdown.
- Evitar "saltos" durante a geração.

### Resultado esperado

A geração deve parecer contínua e natural.

---

# 3. Estados dos Componentes

Todos os componentes interativos devem possuir estados consistentes.

## Botões

- Default
- Hover
- Active
- Focus
- Disabled
- Loading

## Sidebar

- Default
- Hover
- Active
- Focus

## Input

- Empty
- Focus
- Disabled
- Streaming

## ThinkingBlock

- Pensando
- Concluído
- Erro
- Expandido
- Recolhido

---

# 4. Estados da IA

Criar estados padronizados para qualquer modelo.

## Estados

```
● Pensando...

✓ Concluído

↻ Regenerando...

⚠ Erro

■ Cancelado
```

Todos devem utilizar o mesmo componente visual.

---

# 5. Code Blocks

Padronizar completamente os blocos de código.

## Especificação

- Border radius: 12px
- Padding: 16px
- Fonte:
  - JetBrains Mono
  - Fira Code (fallback)
- Nome da linguagem no topo
- Botão "Copiar"
- Scroll horizontal
- Fundo separado da resposta

---

# 6. Padronização do Markdown

Todos os elementos Markdown devem possuir estilo próprio.

## Componentes

- H1
- H2
- H3
- Listas
- Tabelas
- Blockquotes
- Inline Code
- Links
- Imagens
- Task Lists
- Horizontal Rule
- Fórmulas matemáticas (caso implementadas futuramente)

---

# 7. Sistema de Avatares

Preparar a interface para diferentes tipos de mensagens.

## Tipos

- Usuário
- Assistente
- Sistema
- Ferramenta
- Erro
- Plugin (futuro)

Mesmo que inicialmente utilizem o mesmo estilo, manter componentes separados.

---

# 8. Tool Cards (Preparação)

Como o NexusLocal será um agregador de múltiplas LLMs, preparar um componente para execução de ferramentas.

## Exemplos

```
🔍 Pesquisando...

🌐 Navegando...

📄 Lendo arquivo...

🐍 Executando Python...

🧮 Calculando...

🗂 Chamando ferramenta...
```

Criar um componente reutilizável chamado:

```
ToolCard
```

---

# 9. Arquitetura Universal para Múltiplos Modelos

Evitar que a interface dependa do formato bruto retornado por cada modelo.

## Arquitetura

```
LLM
        │
        ▼
Model Adapter
        │
        ▼
Normalized Response
{
    reasoning,
    answer,
    toolCalls,
    metadata
}
        │
        ▼
Componentes da Interface
```

## Objetivo

Cada novo modelo deve precisar apenas de um Adapter.

A interface nunca deve conhecer formatos específicos como:

- `<think>`
- `<analysis>`
- `<reasoning>`
- `<reflection>`
- etc.

---

# 10. Preparação para Métricas

Preparar estrutura para exibição futura de estatísticas.

## Campos previstos

- Tokens gerados
- Tokens de entrada
- Velocidade (tokens/s)
- Tempo total
- Modelo utilizado
- Tempo de reasoning

Mesmo que inicialmente não sejam exibidos, deixar suporte previsto.

---

# 11. Layout Responsivo

Padronizar comportamento em todas as resoluções.

## Desktop

```
largura máxima: 760px
```

## Tablet

```
largura máxima: 680px
```

## Mobile

```
largura: 100%

padding lateral: 16px
```

---

# 12. Scroll e Navegação

Padronizar comportamento do scroll.

## Regras

- Scroll suave.
- Scrollbar discreta.
- Exibir scrollbar apenas quando necessário.
- Manter posição durante streaming.
- Não realizar saltos de conteúdo.

---

# 13. Acessibilidade

Garantir compatibilidade com boas práticas.

## Implementar

- Navegação por teclado
- Focus Ring consistente
- ARIA Labels
- Screen Reader
- Contraste mínimo WCAG AA
- Ordem correta de Tab

---

# 14. Sistema de Design Tokens

Evitar valores fixos espalhados pelo CSS.

## Criar variáveis

### Tipografia

```css
--font-chat
--font-thinking
--font-meta
```

### Opacidade

```css
--opacity-primary
--opacity-secondary
--opacity-thinking
--opacity-meta
```

### Espaçamentos

```css
--space-xs
--space-sm
--space-md
--space-lg
--space-xl
```

### Raios

```css
--radius-chat
--radius-input
--radius-card
```

### Motion

```css
--motion-fast
--motion-normal
--motion-slow
```

Todo o sistema deve consumir estes tokens.

---

# 15. Objetivo Final da Experiência

A interface deve transmitir:

- Clareza
- Calma
- Elegância
- Leveza
- Rapidez
- Foco

O usuário deve conseguir identificar instantaneamente:

1. A resposta principal.
2. O pensamento (quando disponível).
3. O status da IA.
4. Os metadados.
5. As ações disponíveis.

A experiência deve ser consistente independentemente do modelo utilizado (Gemma, Qwen, DeepSeek, Llama, GPT, Claude, etc.).

---

# Critérios de Conclusão

## UX

- Hierarquia visual clara.
- Leitura confortável.
- Pensamento opcional e não intrusivo.
- Interface limpa.

## Performance

- Streaming suave.
- Scroll sem saltos.
- Transições leves.
- Sem perda de desempenho.

## Arquitetura

- Componentes desacoplados.
- Parser universal.
- Model Adapters independentes.
- Design Tokens centralizados.

## Escalabilidade

A adição de novos modelos deve exigir apenas a implementação de um novo Adapter, sem necessidade de alterar os componentes visuais.

---

# Resultado Esperado

Ao final desta fase, o NexusLocal deverá oferecer uma experiência visual comparável às melhores interfaces de IA do mercado, inspirando-se na simplicidade editorial do Claude.ai, na fluidez do ChatGPT e na flexibilidade necessária para suportar dezenas de modelos diferentes por meio de uma arquitetura unificada e escalável.
````
