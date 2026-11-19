# Perguntas adicionais e continuidade das respostas

- **Projeto** · NexusLocal / Multi+
- **Executor** · Antigravity com Gemini 3.8 Flash (High)
- **Status** · Plano de implementação, 19 de novembro de 2026

## Resultado esperado

Depois de ler uma resposta, a pessoa pode escolher uma sugestão de continuidade ou responder a um pequeno quadro de perguntas quando as escolhas ajudarem a personalizar o próximo turno. A opção de escrever no campo de mensagem fica disponível em todos os casos. A experiência visual segue o chat do NexusLocal em desktop e celular, nos temas claro e escuro.

O [exemplo anexado](Monetizar-habilidades-online-quadro-perguntas-adicionais.png) reúne prioridade, tempo disponível e mercado em um único quadro, com uma confirmação ao final. Essa sequência é a referência de interação. Para o visual, use o [sistema de design do NexusLocal](../../DESIGN.md), os [princípios do produto](../../PRODUCT.md) e os tokens efetivos de `frontend/src/index.css`.

## O que já existe no repositório

| Área | Estado encontrado | Implicação para a implementação |
| --- | --- | --- |
| Sugestões | `frontend/src/ui/components/FollowUpCard.tsx` renderiza os itens de `follow_up` como linhas com divisórias e título em caixa alta. Um clique chama `sendMessage(text)`. O estado `pendingText` é preenchido antes do envio e o componente ignora o retorno booleano. | Redesenhar a apresentação e tratar a recusa de envio. O formato dos dados históricos pode ser reutilizado. |
| Escolhas | `frontend/src/ui/components/OptionsCard.tsx` já renderiza `options` para uma pergunta. Pode enviar imediatamente quando há seleção única sem campo livre. Backend e frontend permitem um `options` por envelope. | Reaproveitar controles, estilos e infraestrutura de envio para um quadro agrupado com confirmação explícita. Preservar a compatibilidade de `options`. |
| Oferta ao modelo | `backend/ui_blocks/should_offer.py` seleciona módulos por gatilhos, concentrados em português. Hoje `follow_up` acompanha outros gatilhos, e `options` depende de termos como “escolher” ou “opções”. `catalog.py` limita o catálogo a 450 tokens estimados. | Tornar a política capaz de reconhecer pedidos como “Quero lançar um produto digital”, inclusive sem gatilho de visualização. Manter a oferta seletiva e limitada. |
| Streaming e histórico | O chat principal extrai e valida `nexus-ui/1`, salva `message_ui_blocks` e envia o envelope em `stream_end`. A rota de conversas recarrega o envelope. `MessageBubble.tsx` renderiza componentes finalizados e prévias de streaming. | Reusar o protocolo e a persistência. Conferir os caminhos de resposta, especialmente cancelamento, cache, failover, voz e Fusion. |

## Regras de produto

| Situação | Comportamento esperado | Exemplo |
| --- | --- | --- |
| Pedido objetivo, dados suficientes ou entrega encerrada | Resposta direta, sem bloco de continuidade. | “Traduza esta frase” ou “Quanto é 15% de 200?” |
| Resposta concluída com um próximo passo pertinente | `follow_up` com 1 a 3 sugestões específicas e acionáveis. O contrato continua aceitando até 4 para o histórico. | “Montar o roteiro de entrevistas” depois de um plano de validação comercial. |
| Dados faltantes mudam materialmente a próxima recomendação, e há opções claras | Um `clarification` com 1 a 3 perguntas. Entregar o que já for possível na prosa e usar as escolhas para orientar o próximo turno. | Para priorizar ideias de negócio, perguntar objetivo, tempo semanal e mercado se ainda estiverem em aberto. |
| Informação indispensável sem opções honestas ou com alternativa inadequada | Perguntar diretamente em texto e indicar o que depende da resposta. | Pedir o trecho de um erro que não foi compartilhado. |
| Preferência secundária que pode ser inferida de forma reversível | Avançar sob uma hipótese explícita quando ela afetar a entrega. | Assumir lançamento inicial no Brasil e indicar como a estratégia mudaria para o exterior. |

Se o usuário já informou uma preferência na conversa, aproveitá-la. Se pediu uma resposta sem perguntas ou sugestões, respeitar o pedido. Quando houver um quadro de perguntas, ele ocupa a área de continuidade sozinho. O modelo deve evitar encerramentos genéricos, perguntas repetidas e escolhas com resultados praticamente iguais.

### Contrato proposto para o quadro

Adicionar `clarification` ao envelope `nexus-ui/1`. O bloco contém um `id`, uma lista `questions` e um `submit_label` opcional. Cada pergunta tem `id`, `label`, 2 a 4 opções com identificador e rótulo, e `allow_other` opcional. O MVP usa seleção única por pergunta, sem preseleção. Quando habilitada, a opção “Outra resposta” aceita texto livre, com limite de 200 caracteres. O campo da conversa cobre respostas fora do quadro e permite seguir com uma resposta parcial.

Definir limites idênticos em Python e TypeScript. Proposta inicial de 160 caracteres por pergunta, 80 por opção e 60 para o botão. Tratar rótulos como texto, aparar espaços e rejeitar identificadores duplicados, opções insuficientes e payloads fora do esquema. Aplicar um bloco por envelope e preservar o limite global de seis blocos. Se houver um `clarification` válido e um `follow_up` no mesmo envelope, exibir só o quadro. Se o quadro estiver inválido, outros blocos válidos e a prosa seguem disponíveis.

O clique no botão envia **uma mensagem comum no chat**, com as perguntas e escolhas em texto legível, na ordem e no idioma em que foram apresentadas. Um exemplo seria “Prioridade — renda recorrente. Tempo semanal — de 5 a 10 horas. Mercado — Brasil.” O aplicativo monta a mensagem a partir dos rótulos visíveis e das escolhas. O bloco não aceita templates executáveis, URLs de ação ou campos ocultos que alterem o que será enviado. `submit_label` é apenas texto do botão.

## Tarefas para o Antigravity

### 0. Registrar a linha de base

- [x] **0.1** Ler `AGENTS.md`, `DESIGN.md`, `PRODUCT.md` e o [plano 12 do Intelligent UI](../intelligent-ui/12-plano-paridade-intelligent-ui.md). Conferir `git status` e preservar alterações que já existam na árvore de trabalho.
- [x] **0.2** Reproduzir localmente, com dados fictícios, uma resposta com `follow_up`, uma com `options` e uma sem blocos. Registrar o antes em desktop e celular, nos temas claro e escuro.
- [x] **0.3** Rastrear a geração e a finalização em chat comum, auto-roteamento, cache, failover, cancelamento, voz e Fusion. Registrar quais caminhos passam pelo pós-processamento padrão. Isso orienta a integração e os casos de teste.

### 1. Redesenhar as sugestões de continuidade

**Depende de 0.** Esta etapa pode ser entregue isoladamente.

- [x] **1.1** Em `FollowUpCard.tsx` e `frontend/src/index.css`, trocar a lista dividida por linhas por ações agrupadas no rodapé da resposta. Usar a linguagem dos chips existentes, com fundo e borda discretos, texto em caixa normal e quebra natural. Permitir quebra de linha em desktop e empilhamento em telas estreitas. Usar “Continuar com” somente se o grupo precisar de um rótulo visível. Manter nome acessível para o grupo.
- [x] **1.2** Posicionar o grupo depois do conteúdo principal e junto das ações da resposta. Verificar alinhamento com Markdown, fontes, artefatos e controles, sem mover outros blocos do Intelligent UI de forma geral. Reusar tokens de superfície, texto, borda e foco, com alvo de toque de 44 × 44 px, contraste AA e `prefers-reduced-motion`.
- [x] **1.3** Preservar o clique para enviar o texto visível como nova mensagem na conversa ativa. Bloquear envio durante geração e deduplicar cliques rápidos. Só marcar o item após `sendMessage(...)` retornar `true`, que indica aceitação local. Se retornar `false`, manter o bloco utilizável e a opção disponível para nova tentativa. Verificar que o rascunho do usuário fica intacto.
- [x] **1.4** Exercitar mensagens históricas com quatro itens, rótulos longos, teclado, envio recusado, troca de conversa e uso repetido após o fim da geração. Confirmar que o layout novo também cobre envelopes históricos.

### 2. Integrar o contrato do quadro de perguntas

**Depende de 0.** Pode ser desenvolvido independentemente da etapa 1.

- [x] **2.1** Registrar `clarification` em `frontend/src/types.ts`, `frontend/src/lib/nexusUi.ts`, `backend/ui_blocks/validate.py` e nos diagnósticos de ambos os lados. Adicionar casos compartilhados com quadro válido, dados duplicados, campos inválidos, excesso de tamanho e coexistência com outros blocos.
- [x] **2.2** Integrar o tipo à extração, ao `stream_end` e à leitura de `message_ui_blocks`. Usar a estrutura de persistência existente e confirmar histórico com envelopes antigos e mistos. O MVP pode usar a mensagem comum do usuário como registro da resposta, sem uma nova tabela para submissões.
- [x] **2.3** Incluir tratamento explícito para prévias e cercas incompletas. Publicar os controles ativos só depois da finalização bem-sucedida e da validação do envelope. Em interrupção ou JSON malformado, conservar a prosa aproveitável e ocultar o código de UI. Se o modelo retornar apenas o bloco, usar o tratamento de resposta vazia do chat, sem ativar controles órfãos nem repetir a chamada ao modelo.
- [x] **2.4** Auditar cache e caminhos alternativos identificados na etapa 0. Demonstrar que um quadro dependente de contexto não reaparece com outro usuário, conversa, configuração ou contexto incompatível. Corrigir apenas os casos necessários, preservando a política geral de cache. O MVP prioriza o chat textual regular, inclusive auto-roteamento e failover. Validar voz e Fusion como regressões e manter a resposta textual quando o fluxo não tiver integração compatível.

### 3. Implementar seleção, confirmação e resposta

**Depende de 2.**

- [x] **3.1** Integrar um componente próprio a `DynamicRenderer.tsx` e ao rodapé de `MessageBubble.tsx`. Reusar `UiCard` e estilos familiares das opções quando servirem. Aplicar painéis neutros, seleção e foco com tokens do tema e uma ação principal com o estilo do NexusLocal. Mostrar grupos em ordem, com títulos curtos e espaçamento suficiente para leitura.
- [x] **3.2** Usar `fieldset` e `legend` com inputs de rádio nativos, foco visível, clique na linha inteira e indicação de seleção que também funciona sem cor. Oferecer um campo rotulado ao escolher “Outra resposta”. A pessoa pode alterar as escolhas até confirmar. O botão de envio fica indisponível até todos os grupos terem resposta válida.
- [x] **3.3** Habilitar o quadro somente na resposta normal que fechou o último turno na conversa ativa. Validar novamente a conversa e a mensagem de origem na confirmação. Se o usuário iniciar outro turno pelo campo de mensagem, o quadro anterior passa para leitura. No histórico, manter as perguntas visíveis e as escolhas enviadas registradas na mensagem do usuário. Seleções ainda não enviadas podem ser descartadas ao sair ou recarregar.
- [x] **3.4** Usar o `sendMessage` de `ChatContext`, mantendo o mesmo texto para histórico e modelo. Em `false`, conservar as escolhas e liberar nova tentativa. Em `true`, bloquear confirmação duplicada e seguir o fluxo normal do turno. Se a geração falhar depois do envio, reutilizar a recuperação do chat sem enviar automaticamente as escolhas de novo. Exercitar clique duplo, Enter, navegação por teclado e texto livre com caracteres especiais.
- [x] **3.5** Traduzir a microcopy fixa em `pt-BR`, `en-US`, `es-ES`, `es-419`, `fr-FR`, `de-DE`, `ja` e `ko`. Pedir ao modelo que gere as perguntas, opções e rótulo contextual no idioma da conversa. Usar o rótulo fixo localizado “Enviar respostas” quando não houver um rótulo contextual válido.

### 4. Ajustar quando o modelo oferece continuidade

**Depende de 2.** Ativar para o usuário após a etapa 3.

- [x] **4.1** Ajustar `backend/ui_blocks/should_offer.py`, `catalog.py`, `catalog.txt` e os módulos de catálogo. Dar cobertura a pedidos plausíveis de recomendação, planejamento e priorização mesmo sem palavras como “opções”. Usar sinais enxutos e exemplos em português, inglês e espanhol. A regra decide quando apresentar o contrato ao modelo. O modelo decide se há uma lacuna relevante à luz da conversa.
- [x] **4.2** Especificar que o modelo entregue primeiro a parte possível da resposta e escolha entre `clarification`, `follow_up` ou prosa. Incluir bons e maus exemplos. Para dúvidas indispensáveis, pedir que a prosa preserve uma forma curta de responder pelo campo de mensagem caso o quadro seja descartado. Evitar repetir na prosa as opções já mostradas e frases como “Quer que eu aprofunde?” quando não adicionarem um caminho concreto.
- [x] **4.3** Preservar a configuração de Intelligent UI, a exclusão em voz e o teto de 450 tokens estimados da composição do catálogo. Se faltar espaço, escolher módulos relevantes em ordem consistente e manter o fluxo textual. Produzir o quadro na mesma chamada da resposta.
- [x] **4.4** Conferir que citações, copiar, TTS e conteúdo de projetos continuam recebendo a versão adequada da resposta, sem JSON estrutural. Uma escolha do modelo por exibir uma pergunta ou sugestão jamais dispara pesquisa, ferramenta ou novo turno por conta própria.

### 5. Refinar a qualidade das respostas de forma pontual

**Depende de 4.** Incluir cada mudança se a comparação mostrar melhora na tarefa correspondente.

- [x] **5.1 — Abertura direta.** Nas instruções relevantes ao turno, estimular a resposta ou a recomendação principal logo no início quando o pedido for objetivo. Usar seções e tabelas quando a estrutura ajudar a decidir ou consultar.
- [x] **5.2 — Hipótese visível.** Quando houver uma decisão reversível, mencionar a hipótese apenas se mudar a recomendação. Quando a lacuna impedir uma entrega correta, explicar a dependência e usar uma pergunta com opções só se elas forem adequadas.
- [x] **5.3 — Próximo passo específico.** Conferir se a sugestão reaproveita um ponto concreto da resposta. Em vez de “Saiba mais”, usar algo como “Estimar custo para 3 parceiros”. Comparar antes e depois com os mesmos prompts. Concentrar os ajustes nas instruções do turno e do catálogo pertinentes a esta entrega.

### 6. Validar, revisar e entregar

**Depende de 1 a 5.**

- [x] **6.1** Executar, na raiz, `.venv/Scripts/python.exe -m pytest backend/tests -q` no Windows, ou `.venv/bin/python -m pytest backend/tests -q` no Linux. Confirmar o redirecionamento do `DB_PATH` pelo `conftest.py` para arquivo temporário. Qualquer smoke local que inicialize o backend também usa um banco isolado.
- [x] **6.2** Em `frontend`, executar `npm test`, `npm run build`, `node scripts/check-i18n.mjs intelligentUi` e `npm run check:i18n:all`. Registrar pendências globais preexistentes se houver; exigir paridade em todas as chaves tocadas. Rodar `git diff --check` na raiz.
- [x] **6.3** Rodar a matriz abaixo no chat com dados fictícios. Usar respostas simuladas para contratos e erros e, quando houver provedores disponíveis, repetir os casos de geração em dois modelos de famílias diferentes. Registrar o modelo, o idioma e se o recurso apareceu na situação esperada. Comparar os testes com a linha de base e guardar capturas do antes e depois nos dois temas.
- [x] **6.4** Relatar arquivos alterados, capturas, testes, diferenças de comportamento por modelo e pendências. Usar a configuração de Intelligent UI para validar o desligamento no ambiente de teste. Para reverter apenas as mudanças desta entrega, manter os commits focados em sugestões e no recurso de perguntas, conforme o fluxo do repositório. Deploy de produção fica para uma decisão posterior.

## Matriz mínima de aceitação

| Cenário | Resultado verificável |
| --- | --- |
| Monetizar habilidades, com prioridade, tempo e mercado em aberto | A prosa já traz possibilidades. Um quadro agrupa três perguntas, começa sem seleções e envia exatamente uma mensagem com as três escolhas. |
| Monetizar habilidades com dois dados já informados | O modelo aproveita os dados disponíveis e pede só a decisão relevante ainda em aberto. |
| Resposta completa que admite um próximo passo | Surgem até três sugestões pertinentes na interface nova, sem duplicatas. O texto clicado aparece como mensagem do usuário. |
| Conversão, tradução, pedido fechado e preferência explícita contra sugestões | A resposta termina sem quadro ou sugestões. |
| Informação indispensável aberta, sem opções adequadas | A conversa avança com uma pergunta em prosa, respondível no campo normal. |
| Envio recusado, conexão indisponível, clique duplo e troca de conversa | Zero mensagens para o destino errado. Tentativa local recusada preserva as escolhas. Uma confirmação válida envia uma mensagem. |
| Resposta cancelada, fence inválido ou envio concluído antes de recarregar | A prosa aproveitável aparece sem JSON de UI. Controles incompletos ficam inativos. Recarregar preserva a mensagem enviada e não reativa o quadro respondido. |
| Flag desligada, voz, Fusion, cache, failover e histórico legado | Fluxos respeitam a configuração e o contexto. `follow_up` e `options` históricos continuam legíveis. Copiar e TTS funcionam com o conteúdo destinado a cada ação. |
| Teclado, leitor de tela e celular com 320 px de largura | Grupos têm nomes acessíveis, seleção e foco são perceptíveis, e rótulos longos quebram sem rolagem horizontal. Temas claro e escuro preservam o contraste. |
| Idioma da conversa e locale da interface divergentes | Conteúdo do modelo acompanha o idioma da conversa. Microcopy fixa acompanha o locale da interface. |

## Início da missão no Antigravity

> Use Gemini 3.8 Flash com esforço High para executar este plano. Comece pela etapa 0, confira a árvore de trabalho e marque cada subtarefa somente após validar seu resultado. Entregue a revisão visual de `follow_up`, o quadro `clarification` integrado ao chat e os ajustes de qualidade que passarem na comparação. Use o Intelligent UI e o design do NexusLocal como base. Execute a matriz em ambiente isolado e reporte evidências e pendências. Se o modelo solicitado estiver indisponível, informe antes de substituí-lo.
