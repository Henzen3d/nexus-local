# UX/UI — uso real e atritos

**Convenções:** observado = navegador/API executados; código = comportamento identificado na implementação; hipótese = risco ainda não demonstrado em condições reais. Severidades são do produto (não confundir com a classificação automática do axe). Caminhos e linhas referem-se à base auditada.

## Matriz das personas e cobertura

| Persona / etapa | Resultado | Evidência / limite |
|---|---|---|
| Iniciante: abrir instalação nova | Login sem conta; nenhum administrador semeado; cadastro público 403 | `01-login-{1440,390}.png`, `api-results.json:cadastro_fechado`; bootstrap por script foi necessário |
| Iniciante: conta QA, sem chaves | Modelo aparece selecionado; mensagem acaba em erro de chave após failovers | `02-primeiro-acesso-*`, `03-sem-chave-*` |
| Diário: enviar, Unicode, markup hostil | Envio e exibição funcionam com fake; `<script>` permanece texto, não executa | `05-resposta-1440`, `15-mobile-enviado-390`; fontes incompletas no ambiente |
| Diário: mudar modelo no mesmo chat | Funciona; mensagens subsequentes mostram qa-b | `06-modelos-1440`, `07-troca-modelo-1440` |
| Diário: conversa longa | 160 mensagens via dados sintéticos; poda observada no request real; não rolamos manualmente todo esse histórico | `measurements.json:long_history_requests` |
| Diário: editar/regenerar | Não encontradas ações nem rotas de edição/regeneração de turnos | `U05`; não confundir renomear conversa com editar mensagem |
| Diário: buscar conversa | Busca por título funciona; texto presente só na resposta não encontra | `08-busca-1440`, testes `busca_*` |
| Diário: texto + imagem | Upload dos dois, chips, envio e biblioteca funcionam | `16-anexos-390`, `17-anexos-resposta-390`, `14-biblioteca-*`; interpretação visual não avaliada |
| Power: Fusion 3 modelos | Texto funciona com 3 provedores sintéticos; 1 falha 401 não derruba síntese | `23-fusion-loading-1440`, `24-fusion-done-*`; backend `B06/B07/B15` |
| Power: Projects/RAG | Listagem e detalhe responsivos; estado “Indexado” não distingue ausência de vetores | `10-projetos-*`, `11-projeto-detalhe-*`; `B05` |
| Power: web e cache | Web emite progresso, mas zero fontes após bloqueio externo; cache testado em módulo isolado | `api-results.json:web_search_rede_bloqueada`, `logic-results.json`; sem validação generativa real |
| Descuidado: vazio, gigante, duplicado | Vazio rejeitado; gigante chega ao provedor; duplicado WS cria 2 conversas | `api-results.json`; duplo clique físico não foi comprovado, só duplicação do protocolo |
| Descuidado: arquivo enorme/corrompido | 26 MiB rejeitado; PDF corrompido tem comportamentos diferentes entre chat e projeto | `18-upload-erro-390`, `B12` |
| Descuidado: parar/fechar/erro de rede | “Parar” só interrompe UI; resposta completa reaparece ao reload. Fechar conexão interrompeu fake em teste separado | `19–22`, `measurements.json`, `B11`; reconexão offline integral não concluída |
| Descuidado: chave inválida/modelo ausente/rede lenta | 401 de fake, modelo inexistente, 429 e stream artificialmente lento exercitados | `api-results.json`, `19-stream-lento-1440`; não são medições de APIs reais |

## U01 — O iniciante não consegue chegar à primeira resposta

**Severidade: alto · observado + código · confiança alta.**

- **Evidência:** banco novo com zero usuários; `api-results.json:cadastro_fechado` retorna 403. `backend/routers/auth.py:37–42` fecha registro; `backend/database.py:928–937` promove usuário existente, não cria o primeiro. `README.md:Quick Start` orienta abrir e configurar chaves, sem explicar bootstrap. `03-sem-chave-1440.png` mostra modelo escolhido antes de verificar uma chave utilizável.
- **Impacto:** instalação parece quebrada; usuário sem conhecimento de Python/SQLite não começa. Além disso, o launcher falha (`B01`).
- **Reprodução:** seguir README com DB novo, abrir login; depois criar conta QA e enviar “Olá” sem chaves.
- **Correção sugerida:** comando de bootstrap idempotente documentado, secreto e sem senha padrão; assistente “1. conta / 2. provedor / 3. testar conexão / 4. primeira mensagem”. Não prometer cadastro aberto sem decisão de produto. Modelo visível não deve significar modelo pronto; exibir pré-requisito e CTA direto para configuração.

## U02 — Erros expõem chave de tradução e diagnóstico confuso

**Severidade: médio · observado · confiança alta.**

- **Evidência:** `03-sem-chave-*` e `05-ollama-sem-chave-1440.png`: título literal **`chat.generationError`**. `frontend/src/components/MessageBubble.tsx:371` chama uma chave ausente da referência de tradução. Failovers anunciam “esgotado” para erro de configuração/chave; log mostra também `Illegal header value b'Bearer '` (`B02`). `i18n.log` registra lacunas em seis locales; isso não prova que toda tradução esteja quebrada.
- **Impacto:** usuário não diferencia falta de configuração, indisponibilidade, limite e defeito interno; mensagens repetidas disputam atenção.
- **Reprodução:** enviar sem chave ou usando Ollama sem chave. Comparar erro inline e toasts.
- **Correção:** taxonomia `configuration/auth/quota/network/context/internal`, texto localizado com ação específica, código de suporte discreto, deduplicação de toasts. Validar referências `t()` além da comparação entre arquivos de locale.

## U03 — Controles sem nome acessível e foco em conteúdo oculto

**Severidade: alto · observado por axe + DOM · confiança alta.**

- **Evidência:** `axe-09-home-1440.json`: dois `button-name` e `nested-interactive`; `axe-12-chat-1440.json`: quatro botões sem nome; `axe-10-projetos-*.json`: `select-name`; mobile `axe-09-home-390.json`: `aria-hidden-focus`; `axe-13-ferramentas-390.json`: quatro `aria-required-parent`. `Sidebar.tsx:674` usa `aria-hidden` e `:930–975` mantém controles interativos aninhados no perfil. Tooltips visuais não garantem nome acessível.
- **Impacto:** pessoas que usam teclado/leitor de tela podem focar em navegação escondida ou ouvir “botão” sem função.
- **Reprodução:** executar `browser_panels.py`; abrir sidebar, projetos e menu “+”; rodar axe com WCAG2A/AA/2.1AA. Validar manualmente Tab/Shift+Tab depois da correção.
- **Correção:** `aria-label` em botões de ícone; `label`/`aria-label` em select; retirar interação do contêiner de perfil que contém outros botões; usar `inert`/desmontagem na sidebar fechada; menu com semântica completa ou lista de botões sem papéis incompatíveis. Focus trap/retorno no modal e bottom sheet. Leitor de tela real ficou pendente.

## U04 — Contraste e alvos de toque abaixo do objetivo

**Severidade: médio · observado/medido · confiança alta.**

- **Evidência:** axe mediu seleção coral sobre cinza **2,82:1**, status “Indexado” verde/branco **3,49:1**, badge de modelo **3,15:1**, metadados cinza **4,47:1**. Ver `axe-11-projeto-detalhe-*`, `axe-12-chat-1440.json`. DOM em `02-primeiro-acesso-1440.json`: buscar/recolher/fechar = **32×32**, modelo = **32 px** de altura; CTA “Entendi” = 41 px. Composer principal “+” e microfone têm 44×44, um ponto positivo.
- **Impacto:** baixa legibilidade de estado, mais toques errados. Não classificar um alvo menor como violação universal de WCAG 2.1 AA: aqui a referência adicional é a meta de ≥44 px solicitada.
- **Reprodução:** inspecionar `getBoundingClientRect()` e rodar axe; comparar com `DESIGN.md:786–790`, que contém exemplos de 36/40 px em conflito com essa meta.
- **Correção:** alvos efetivos 44×44 sem inflar ícones; tokens de texto com ≥4,5:1 para corpo pequeno, ≥3:1 para componentes/gráficos pertinentes; selecionar com `--selection`, não com texto coral de baixo contraste. Retestar ambos os temas.

## U05 — Fluxo diário sem edição/regeneração e busca restrita ao título

**Severidade: médio · observado + inspeção de código · confiança alta.**

- **Evidência:** `07-troca-modelo-1440.png`/`12-chat-1440.png`: copiar e ouvir, sem editar/regenerar. Ações de `MessageBubble.tsx` não implementam revisão do turno; rotas de `backend/routers/conversations.py` cobrem ler/renomear/favoritar/excluir/associar projeto. A busca em `:40–42` usa somente `c.title LIKE ?`. `api-results.json:busca_conteudo_nao_titulo` retorna `[]` para texto presente nas respostas.
- **Impacto:** correções de prompt e tentativas alternativas exigem copiar/reenviar; histórico de raciocínio fica poluído. Encontrar conversa por assunto mencionado posteriormente falha.
- **Reprodução:** abrir chat com resposta, passar mouse/foco pelas ações; procurar “Conteúdo determinístico” nas conversas após resposta do fake.
- **Correção:** regeneração como nova variante ligada ao turno, edição com branch explícito e preservação do histórico anterior; busca full-text no corpo com snippet e título. Não apagar silenciosamente descendentes.

## U06 — “Parar” altera a interface, não o trabalho

**Severidade: alto · observado · confiança alta.**

- **Evidência:** `19-stream-lento-1440.png` → `20-stop-1440.png` → `21-stop-reload-1440.png`. Após tocar Parar, o fake completou em **16,365 s** e o texto integral reapareceu ao reabrir a conversa. `useChat.ts:422–451` só altera estado local; detalhes técnicos em `B11`.
- **Impacto:** custo continua, percepção de controle é falsa, texto parcial difere do histórico salvo. Novo envio enquanto o backend ainda gera pode misturar estados sem IDs de turno.
- **Reprodução:** selecionar `qa-slow`, enviar, esperar primeiro token, clicar “Parar”, esperar 17 s e recarregar.
- **Correção:** cancelar por `turn_id` e aguardar confirmação; mostrar “Cancelando…” → “Interrompido”; persistir trecho parcial com estado próprio e nunca ressuscitar resposta completa em reload.

## U07 — Onboarding promete privacidade que o pipeline não garante

**Severidade: alto · observado + código · confiança alta.**

- **Evidência:** `02-primeiro-acesso-*.png` diz **“Tudo fica na sua máquina — sem enviar memória para a nuvem.”** Texto em `frontend/src/i18n/locales/pt-BR.json:874`. `backend/orchestration/build_context.py:214–232` sanitiza parte da memória para provedores externos, mas monta bloco de contexto que segue no request. `chat.py:523–537,582–609` envia esse system ao provedor/Fusion.
- **Impacto:** consentimento baseado em informação incorreta; perfil/memórias permitidas podem sair da máquina. Não foi transmitido dado pessoal real neste teste.
- **Reprodução:** ler onboarding e rastrear `build_memory_context` até `provider.stream_chat`; conferir que sanitização não é “zero transmissão”.
- **Correção:** “armazenado localmente; trechos relevantes podem ser enviados ao provedor escolhido”; mostrar destino e categorias, opção local-only, exclusão/inspeção fáceis. Política por participante do Fusion, não só pelo modelo selecionado (`B14`).

## U08 — Estados terminais enganosos no Fusion e na busca

**Severidade: médio · observado + código · confiança alta.**

- **Evidência:** `24-fusion-done-*` e `25-dark-*`: resposta já completa, card ainda **“Consolidando…”**. `FusionStatusCard.tsx:142–149` depende de `allDone` dos proposers, não do estado terminal do juiz. A resposta é rotulada qa-a mesmo sendo qa-judge na fixture; o evento final do Fusion não leva os mesmos metadados do caminho normal. Em `api-results.json:web_search_rede_bloqueada`, etapa “completed” com zero fontes e `web_search_used=false`; `backend/web_search/agent.py:44–55` emite completed no `finally` até em falha.
- **Impacto:** não se sabe se terminou, qual modelo respondeu e se a pesquisa realmente trouxe evidências.
- **Reprodução:** enviar Fusion de três modelos e esperar fim; fazer busca com internet indisponível.
- **Correção:** estados `queued/running/succeeded/empty/failed/cancelled`, modelo efetivo na mensagem e resumo de participantes; “Busca sem resultados” separado de “Busca indisponível”. Não atribuir “erro” a uma busca legitimamente vazia.

## U09 — Consistência visual e carregamento ainda precisam de uma referência única

**Severidade: baixo (visual) / médio (carregamento) · observado + código · confiança média-alta.**

- **Evidência:** `DESIGN.md:422–454` define superfícies neutras e seleção azul; logo, branco/cinza **não** é desvio por não ser creme. `:663` exige ação de envio coral, mas `11-projeto-detalhe-390.png` mostra botão preto (`index.css:8379`). `index.css:6847–6855` colore navegação selecionada em coral. O sistema usa Cormorant Garamond/Inter (`frontend/index.html:17–19`), substitutos autorizados pelo DESIGN; não é correto exigir EB Garamond exclusivamente. `build.log`: chunk principal **1.659,42 kB / 483,71 kB gzip**; imports de painéis em `App.tsx:8–17` são eager.
- **Impacto:** sinais de seleção/ação inconsistentes; conexão móvel fria paga por áreas que ainda não abriu. Não foi medido LCP em celular físico.
- **Reprodução:** comparar projeto, biblioteca, chat e ambos os temas; rodar build e inspecionar recursos/fonts.
- **Correção:** reconciliar contrato de DESIGN e tokens antes de mexer nas cores; lazy-load de admin/projetos/dashboard; fontes locais licenciadas e subsets adequados à distribuição self-hosted. Falha de Google Fonts neste sandbox é limitação ambiental, não evidência de falha universal.

## Leitura visual e microinterações

- **Pontos positivos:** cartões e espaçamento consistentes, hierarquia serif/sans identificável, navegação mobile em drawer, ferramentas em bottom sheet, chips de anexos e biblioteca em duas colunas; troca de modelo preserva conversa. Screenshots `10–17` mostram esses fluxos funcionando.
- Nas telas Fusion medidas, `scrollWidth == innerWidth` tanto em 1440 quanto em 390. Não foi observado overflow horizontal nessas capturas; isso não valida toda string longa em toda tela.
- Loading do stream e transição para resposta são perceptíveis; o cancelamento/estado final contraditório é mais urgente do que aperfeiçoar animações.
- Snapshots são estados estáticos. Duração/fluidez de animações, reduced-motion, teclado virtual, gestos em hardware, zoom 200% e navegação completa com leitor de tela devem entrar na regressão.
- `12-chat-390.png` registra o rascunho após Enter (mobile insere quebra); o envio por toque foi validado separadamente em `15-mobile-enviado-390.png`. Não tratar o primeiro snapshot como envio concluído.
