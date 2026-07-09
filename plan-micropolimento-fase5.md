# Plano de Execução — NexusLocal Fase 5: Microinterações e Polimento Visual

## Objetivo

Elevar a percepção de qualidade da interface do NexusLocal através de motion design consistente, estados padronizados, tipografia/opacidade em escala e arquitetura de adapters por modelo — sem adicionar novas funcionalidades, aproximando a experiência do padrão Claude.ai/ChatGPT.

## Escopo

**Dentro:**
- Design tokens (cor, tipografia, opacidade, espaçamento, raio, motion)
- Motion design e streaming
- Estados de componentes e da IA
- Code blocks e Markdown
- Avatares e ToolCard
- Arquitetura Model Adapter → Thinking Parser → UI
- Responsividade, scroll e acessibilidade

**Fora:**
- Novas funcionalidades de produto (Fusion, prompt enhancer, web search, etc. — tratadas em outros planos)
- Mudanças de backend/API além do necessário para expor metadados (tokens/s, tempo de reasoning)

**Legenda de modelos:** Gemini 3.1 Pro (High) = raciocínio arquitetural/algorítmico pesado · Gemini 3.1 Pro (Low) = engenharia de software padrão · Gemini 3.5 Flash (Low) = tradução/replicação mecânica de padrões já validados.

---

## Fase 1 — Design Tokens (base de tudo)

**Fase 1.1 — Definição da escala tipográfica**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: É enumeração de valores (20/16/16/14/13/12/15px) sem decisão arquitetural — qualquer modelo executa com precisão.
Dica de Cota: Peça direto a lista de variáveis CSS já nomeadas; não precisa de raciocínio, apenas formatação correta.
Verificar: `--font-*` cobre heading, título, mensagem, código, thinking, meta, placeholder.

**Fase 1.2 — Definição da escala de opacidade**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Mesma natureza da 1.1: valores fixos (100/72/65/55/38%) sem ambiguidade de design.
Dica de Cota: Combine com 1.1 no mesmo prompt/arquivo para economizar uma chamada inteira.
Verificar: cada opacidade mapeia a um uso claro (texto primário, secundário, thinking, meta, disabled).

**Fase 1.3 — Definição de tokens de motion, espaçamento e raio**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Valores já especificados no documento-fonte (120/180/220ms, `ease-out`); é transcrição para CSS.
Dica de Cota: Um único prompt gerando os três arquivos (`motion.css`, `spacing.css`, `radius.css`) evita 3 chamadas separadas.
Verificar: nenhuma transição excede 250ms; nenhum valor de espaçamento/raio hardcoded fora dos tokens.

**Fase 1.4 — Consolidação em `tokens/index.css` e integração no build**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Exige tocar no entrypoint/build da aplicação e garantir que a ordem de import não gere conflito de cascata — engenharia de software real, mas não arquitetural.
Dica de Cota: Envie apenas a estrutura de pastas atual + os 4 arquivos de tokens gerados; não reenvie o restante do CSS da aplicação.
Verificar: build roda sem erro; variáveis aparecem em `:root` no DevTools.

---

## Fase 2 — Motion Design nos Componentes

**Fase 2.1 — Mapeamento de componentes → token de motion**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: É uma tabela de decisão (botão→fast, sidebar→slow, thinking→normal) sem lógica condicional.
Dica de Cota: Peça a tabela em Markdown antes de qualquer código; usa-se como referência para 2.2 sem reconsultar modelo caro.
Verificar: tabela cobre botões, sidebar, ThinkingBlock, input, dropdowns, tooltips.

**Fase 2.2 — Implementação das transições CSS por componente**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Precisa editar CSS existente sem quebrar especificidade/seletores já em produção.
Dica de Cota: Envie apenas o CSS do componente sendo alterado por vez, não o design system inteiro.
Verificar: interagir com sidebar/ThinkingBlock/menus e confirmar visualmente que nada é instantâneo ou "salta".

**Fase 2.3 — QA visual das transições**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Checklist de observação comparando comportamento real com a tabela da 2.1.
Dica de Cota: Tarefa majoritariamente manual (visual); use o modelo só para gerar o checklist de teste, não para "assistir" a interface.
Verificar: nenhuma animação chamativa ou acima de 250ms percebida.

---

## Fase 3 — Streaming da Resposta

**Fase 3.1 — Especificação do cursor piscante e regra de auto-scroll**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Envolve uma regra condicional (só rolar automaticamente se o usuário já está no fim) — lógica de produto simples, mas não trivial.
Dica de Cota: Descreva o comportamento em texto puro; não é necessário enviar código de streaming existente ainda.
Verificar: especificação cobre os 2 estados (usuário no fim vs. usuário scrollado para cima).

**Fase 3.2 — Algoritmo de renderização progressiva de Markdown (streaming-safe)**
Complexidade: Alta · Modelo Sugerido: Gemini 3.1 Pro (High)
Justificativa: Parsear Markdown incrementalmente sem re-renderizar tudo a cada chunk, sem quebrar blocos abertos (ex.: um code fence ainda não fechado), é um problema algorítmico não-trivial com múltiplos edge cases.
Dica de Cota: Peça só o algoritmo/pseudo-código + implementação isolada da função de parsing; não envie o restante da UI. Salve a saída localmente — ela vira contexto fixo para as próximas subtarefas.
Verificar: gerar resposta longa com markdown misto (listas, código, tabelas) e confirmar que nada quebra durante o streaming.

**Fase 3.3 — Integração do parser com scroll suave**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: É colagem entre a lógica da 3.2 (já pronta) e a regra da 3.1 — trabalho de integração, não de design de algoritmo.
Dica de Cota: Forneça a função da 3.2 como "contexto fixo estático"; não peça para o modelo reescrevê-la.
Verificar: scroll acompanha suavemente sem reposicionamento abrupto.

**Fase 3.4 — Testes de regressão com respostas longas**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Geração de casos de teste (respostas de 1000+ tokens, markdown pesado) é trabalho mecânico.
Dica de Cota: Peça apenas os casos de teste em lista; execução é manual/local.
Verificar: cursor some ao concluir; sem "saltos" de layout em nenhum caso testado.

---

## Fase 4 — Estados de Componentes e da IA

**Fase 4.1 — Especificação da máquina de estados (Botão, Sidebar, Input)**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Precisa garantir que os estados sejam mutuamente consistentes entre componentes (ex.: Disabled nunca coexiste com Hover) — exige alguma disciplina de design de sistema.
Dica de Cota: Peça uma tabela estado × componente × classe CSS; reaproveite os tokens da Fase 1 no prompt.
Verificar: tabela cobre Default/Hover/Active/Focus/Disabled/Loading para os 3 componentes.

**Fase 4.2 — Implementação CSS dos estados**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Tradução direta da tabela da 4.1 para classes CSS, sem decisão nova.
Dica de Cota: Envie só a tabela da 4.1 como input; o Flash replica fielmente.
Verificar: cada estado renderiza visualmente distinto ao ser forçado manualmente.

**Fase 4.3 — Criação do componente único `AIStatusIndicator`**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Precisa suportar 5 variantes (Pensando/Concluído/Regenerando/Erro/Cancelado) num único componente parametrizável, evitando duplicação de código — decisão de arquitetura de componente.
Dica de Cota: Peça o componente com uma prop `status: enum`; não peça 5 componentes separados.
Verificar: trocar a prop `status` muda ícone/texto/cor sem trocar de componente.

**Fase 4.4 — QA de todos os estados**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Checklist de verificação visual contra a especificação.
Dica de Cota: Gere o checklist uma vez; reutilize para toda a Fase 4.
Verificar: todos os 5 estados da IA e os estados dos 3 componentes usam o mesmo padrão visual.

---

## Fase 5 — Code Blocks e Markdown

**Fase 5.1 — Especificação do componente `CodeBlock`**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Precisa decidir comportamento do botão "Copiar" (feedback visual, fallback sem clipboard API) e fallback de fonte — pequenas decisões de UX que afetam a API do componente.
Dica de Cota: Peça a interface/props do componente antes da implementação completa.
Verificar: especificação cobre padding 16px, radius 12px, fonte JetBrains Mono/Fira Code, nome da linguagem, scroll horizontal.

**Fase 5.2 — Implementação do `CodeBlock`**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Uma vez definida a props/API na 5.1, é implementação direta.
Dica de Cota: Forneça a spec da 5.1 como contexto fixo; não repita a decisão de design.
Verificar: renderizar bloco de código real e testar botão copiar.

**Fase 5.3 — Padronização de estilos Markdown (H1–H3, listas, tabelas, blockquote, links, imagens, task lists, hr)**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Estilização de elementos padrão de Markdown usando os tokens já definidos na Fase 1 — trabalho mecânico de CSS.
Dica de Cota: Envie a lista de elementos + tokens; não precisa de nova decisão de design.
Verificar: renderizar mensagem de teste contendo todos os elementos listados.

**Fase 5.4 — Teste de renderização integrada**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Geração de payload de teste (mensagem markdown "kitchen sink").
Dica de Cota: Um único prompt gera o markdown de teste completo, reaproveitável em Fases futuras.
Verificar: comparação visual direta contra a especificação, elemento por elemento.

---

## Fase 6 — Avatares e ToolCard

**Fase 6.1 — Especificação de variantes do `ToolCard`**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: É mapeamento de ícone → texto → tipo de ferramenta (Pesquisando, Navegando, Executando Python etc.), sem lógica nova.
Dica de Cota: Peça a tabela de variantes junto com a Fase 2.1 se possível, para economizar chamadas.
Verificar: tabela cobre as 6 variantes do documento original + espaço para futuras.

**Fase 6.2 — Implementação do componente `ToolCard` reutilizável**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Precisa aceitar variantes dinamicamente (prop-driven) para suportar ferramentas futuras sem refatoração — pequena decisão de arquitetura de componente.
Dica de Cota: Reaproveite o padrão de "componente único + enum de variante" já usado no `AIStatusIndicator` (4.3) como exemplo no prompt.
Verificar: trocar a variante não exige alterar o componente base.

**Fase 6.3 — Criação dos componentes de Avatar separados**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Componentes visualmente idênticos por ora, apenas com nomes/tipos distintos (Usuário, Assistente, Sistema, Ferramenta, Erro, Plugin) — trabalho mecânico.
Dica de Cota: Peça os 6 componentes num único arquivo/prompt.
Verificar: cada tipo de mensagem renderiza o avatar correspondente.

---

## Fase 7 — Arquitetura de Adapters (mudança estrutural mais importante)

**Fase 7.1 — Especificação do Contrato Rígido (Interface `NormalizedResponse`)**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (High)
Justificativa: O design desse contrato de dados dita o sucesso de todo o ecossistema do NexusLocal. Definir exatamente as tipagens abstratas de `reasoning`, `answer`, `toolCalls` e `metadata` exige uma visão arquitetural apurada para que nenhum componente de UI quebre no futuro. Sendo o cérebro da operação de engenharia, ele precisa do modelo Pro mais capaz.
Dica de Cota: Controle de entrada rígido. Não envie arquivos de código da interface para o modelo. Escreva um prompt puramente conceitual listando o comportamento esperado dos modelos (Gemma, Qwen, DeepSeek) e peça apenas a interface TypeScript purificada. Isso gastará uma fração mínima de tokens da sua cota High.
Verificar: interface cobre `reasoning`, `answer`, `toolCalls`, `metadata` sem campos específicos de nenhum modelo.

**Fase 7.2 — Arquitetura e Algoritmo do `ThinkingParser` Intermediário**
Complexidade: Alta · Modelo Sugerido: Gemini 3.1 Pro (High)
Justificativa: Esta é a peça lógica mais complexa da Fase 7. Desenvolver um parser capaz de isolar expressões regulares e extrair blocos de tags mutáveis (`<think>`, `<analysis>`, etc.) de forma incremental durante o streaming, sem corromper a string final, exige alta capacidade algorítmica de múltiplas camadas.
Dica de Cota: Ponto crítico do projeto. Após o Gemini 3.1 Pro (High) entregar a lógica central de tratamento e herança do parser, salve essa saída em um arquivo local imediatamente. Você usará esse código gerado como "contexto fixo estático" para os modelos mais baratos nas próximas subtarefas, proibindo re-consultas ao modelo High.
Verificar: alimentar o parser com stream simulado contendo tags parciais/incompletas e confirmar que a string final nunca é corrompida.

**Fase 7.3 — Estruturação da Classe Abstrata Base `ModelAdapter`**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Uma vez que o contrato (`NormalizedResponse`) e o `ThinkingParser` foram definidos pelo modelo anterior, criar a classe abstrata que servirá de molde para os adapters exige apenas engenharia de software tradicional. O Gemini 3.1 Pro (Low) resolve essa padronização com extrema fidelidade e com metade do custo de tokens.
Dica de Cota: Forneça como exemplo ao modelo apenas a interface gerada na Fase 7.1. Mantenha as instruções diretas e focadas na herança de classes.
Verificar: a classe abstrata força a implementação de um método que retorna `NormalizedResponse` em qualquer subclasse.

**Fase 7.4 — Implementação do Primeiro Adapter Concreto (Prova de Conceito: `GemmaAdapter`)**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: É a colagem prática da arquitetura. O modelo precisa ler a saída bruta real do Gemma e aplicar as regras do `ThinkingParser` para testar o fluxo de ponta a ponta. O Pro (Low) tem o balanço ideal de capacidade lógica para debugar os primeiros problemas de integração sem queimar cartucho caro.
Dica de Cota: Se o comportamento de stream do Gemma apresentar anomalias (como blocos cortados), faça o debug manual ou use prompts curtos de correção. Não reenvie toda a arquitetura no prompt de erro.
Verificar: trocar de modelo na interface para Gemma exibe reasoning/answer corretamente separados via o pipeline completo.

**Fase 7.5 — Replicação de Adapters Secundários (`QwenAdapter`, `DeepSeekAdapter`)**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Esta subtarefa vira um trabalho puramente braçal de cópia e adequação. Como a estrutura do `GemmaAdapter` já estará validada e funcional, basta pedir para o Flash (Low) replicar a exata mesma lógica, alterando apenas os delimitadores de string específicos do Qwen ou DeepSeek. O Flash (Low) executará essa tradução de código de forma quase gratuita para a sua cota.
Dica de Cota: Forneça o código pronto do `GemmaAdapter` e diga explicitamente: "Crie o QwenAdapter seguindo estritamente este padrão, alterando apenas a tag X pela tag Y". O Flash resolverá em um único turno ultra-rápido.
Verificar: trocar entre Gemma/Qwen/DeepSeek na interface não exige nenhuma alteração em componentes visuais — apenas o Adapter muda.

---

## Fase 8 — Metadados e Métricas (estrutura, sem exibição obrigatória)

**Fase 8.1 — Especificação do schema estendido de `metadata`**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: É extensão aditiva do contrato já definido na 7.1 (tokens gerados, tokens de entrada, tokens/s, tempo total, modelo, tempo de reasoning) — não exige nova decisão arquitetural.
Dica de Cota: Envie apenas a interface `NormalizedResponse` da 7.1 e peça o campo `metadata` expandido; não reabra a Fase 7 inteira.
Verificar: schema cobre os 6 campos previstos no documento original.

**Fase 8.2 — Instrumentação dos Adapters para popular `metadata`**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Requer calcular tokens/s e tempos a partir dos timestamps de streaming — lógica simples, mas tocando código já existente dos Adapters.
Dica de Cota: Edite um Adapter por vez (reaproveitando o padrão da Fase 7.5); não peça para instrumentar todos de uma vez.
Verificar: logar `metadata` no console para uma resposta real confirma todos os campos preenchidos corretamente.

**Fase 8.3 — Preparação do componente de exibição (oculto por flag)**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Componente de exibição simples, controlado por feature flag, sem lógica de negócio.
Dica de Cota: Peça o componente já com a prop `visible={false}` por padrão.
Verificar: ativar a flag manualmente exibe os campos sem quebrar layout.

---

## Fase 9 — Responsividade, Scroll e Acessibilidade

**Fase 9.1 — Definição de breakpoints e larguras máximas**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Valores fixos já definidos (760px/680px/100%+16px) — transcrição.
Dica de Cota: Combine com a criação dos tokens de espaçamento (Fase 1.3) se ainda não tiver sido feito.
Verificar: inspecionar em 3 tamanhos de viewport reais.

**Fase 9.2 — Implementação de scrollbar discreta e scroll suave**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: CSS padrão (`scroll-behavior: smooth`, `::-webkit-scrollbar` customizada) sem lógica de aplicação.
Dica de Cota: Peça um snippet CSS reutilizável aplicável a qualquer container com overflow.
Verificar: scrollbar só aparece durante interação de scroll ativo.

**Fase 9.3 — Navegação por teclado, ARIA labels e focus ring**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Exige mapear a ordem de Tab correta entre componentes interativos (sidebar, input, botões, ThinkingBlock) — requer entender a estrutura real da árvore de componentes, não é trivial.
Dica de Cota: Envie apenas a árvore de componentes (nomes e hierarquia), não o código completo de cada um.
Verificar: navegar toda a interface usando apenas o teclado, sem mouse.

**Fase 9.4 — Auditoria de contraste WCAG AA**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Cálculo de contraste é mecânico dado os valores de opacidade/cor já definidos na Fase 1.
Dica de Cota: Peça apenas a lista de combinações texto/fundo que falham o AA, com base nas cores e opacidades já geradas.
Verificar: nenhuma combinação texto/fundo abaixo do mínimo AA (4.5:1 para texto normal).

---

## Fase 10 — Verificação Final (sempre por último)

**Fase 10.1 — Checklist de revisão visual (clareza, calma, elegância, leveza, rapidez, foco)**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Geração de um checklist de inspeção manual a partir dos critérios já descritos no documento original.
Dica de Cota: Peça o checklist uma única vez; reutilize em todas as revisões futuras do produto.
Verificar: revisão manual da interface completa contra o checklist.

**Fase 10.2 — Teste cross-model de consistência visual (Gemma/Qwen/DeepSeek)**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Requer comparar comportamento real de 3 pipelines de Adapter diferentes e identificar divergências sutis de UI — mais do que checklist simples, mas não exige o modelo High.
Dica de Cota: Rode o teste localmente e só use o modelo para analisar/triagem de eventuais divergências reportadas.
Verificar: trocar entre os 3 modelos não altera nenhum componente visual, apenas o conteúdo.

**Fase 10.3 — Auditoria de performance (streaming, scroll, transições)**
Complexidade: Baixa · Modelo Sugerido: Gemini 3.5 Flash (Low)
Justificativa: Checklist mecânico contra os limites já definidos (≤250ms, sem jank, sem saltos).
Dica de Cota: Reaproveite o checklist da Fase 2.3 e da Fase 3.4, apenas consolidando.
Verificar: nenhum jank perceptível durante streaming; nenhuma transição acima de 250ms.

**Fase 10.4 — Code review final (tokens e acoplamento de modelo)**
Complexidade: Média · Modelo Sugerido: Gemini 3.1 Pro (Low)
Justificativa: Exige varrer o código em busca de valores fixos fora dos design tokens e de qualquer componente de UI que ainda referencie um formato de modelo específico (`<think>` etc.) — checagem estrutural, não apenas visual.
Dica de Cota: Peça ao modelo uma lista de padrões suspeitos para grep (ex.: `px` fora de var(), `<think>` fora dos Adapters) em vez de enviar todo o código-fonte para leitura integral.
Verificar: grep retorna zero ocorrências de valores fixos fora dos tokens e zero referências a formatos de modelo específico fora da camada de Adapters.

## Concluído Quando

- [x] Todas as fases 1–9 completas e verificadas.
- [x] Interface aprovada visualmente contra a especificação original (micropolimento.md) e as adições de UX (tipografia, opacidade, adapters em duas camadas).
- [x] Nenhuma regressão nas funcionalidades existentes do NexusLocal.

---

## Notas

- A arquitetura de duas camadas (**Model Adapter → Thinking Parser → UI**) substitui a proposta original de "Parser Universal" único — é a mudança de maior impacto de longo prazo, pois isola a UI de qualquer formato bruto de modelo (`<think>`, `<analysis>`, etc.).
- Fórmulas matemáticas no Markdown ficam previstas na Fase 5, mas não implementadas nesta rodada.
- Este plano assume que a Fase 4 anterior (refatoração estrutural: ThinkingBlock, hierarquia visual, layout, sidebar) já está concluída, conforme indicado no documento original.
- **Estratégia geral de cota:** reserve o Gemini 3.1 Pro (High) exclusivamente para as subtarefas 3.2, 7.1 e 7.2 — as únicas com complexidade algorítmica/arquitetural real. Todo o resto do plano é resolvível com Pro (Low) ou Flash (Low), desde que a saída do modelo High seja salva localmente e reutilizada como contexto fixo, nunca reconsultada.