# 📦 Planos Descartados / Arquivados — JEV-Fast

Este diretório contém os planos da pasta `melhorias/jev-fast` que foram **descartados ou arquivados durante a auditoria técnica** de implementação no NexusLocal.

Para o relatório completo e detalhado com as alternativas adotadas e o novo código em produção, consulte:
👉 [CONSOLIDACAO-JEV-FAST.md](file:///j:/Arquivos%20Osmar/Multi+/melhorias/jev-fast/CONSOLIDACAO-JEV-FAST.md)

---

### Resumo dos Motivos de Descarte:

| Arquivo | Título Original | Motivo do Descarte | O que foi feito em vez disso |
|---|---|---|---|
| `01-early-exit.md` | Early Exit para Triviais | Premissa incorreta: alegava que `classify_intent` fazia 31ms de queries SQL (já era regex em RAM <0.2ms). Além disso, não retornava resposta imediata. | Implementado o Fast Greeting Bypass em `chat.py`, pulando 3 queries de histórico para saudações curtas sem anexos. |
| `04-batch-query.md` | Batch Query Unificada | SQL incorreto: tabelas e colunas inexistentes (`memories`, `relevance`), `LEFT JOIN 1=1` cartesiano e quebra da busca híbrida (FTS5 BM25 + Vetorial). | Mantida a busca híbrida nativa, com reuso do vetor em RAM via `RequestContext` (JEV #19). |
| `07-executor-deterministico.md` | Executor Determinístico | Degradação do produto: propunha interceptar `/imagem` para gerar código SVG simples em vez de chamar modelos generativos (Flux). | Mantida a esteira de difusão/Flux com desacoplamento assíncrono para não travar a conversa. |
| `08-validacao-recuperacao.md` | Validação e Recuperação | Perigoso para o chat: adiciona verificadores heurísticos no caminho de resposta, gerando retries indevidos, consumo excessivo de cotas e risco de duplicação de ações. | Validação deve ser orientada por schema estrito (ex: JSON) apenas em ferramentas estruturadas, nunca heurística livre no chat. |
| `12-parallel-preprocessing.md` | Paralelização do Pré-Processamento | Código inválido e risco de concorrência: exemplos usavam atributos e métodos inexistentes no `RequestContext`, ignoravam dependência da chave semântica com o fingerprint de memória e causavam locks no SQLite. | Execução sequencial mantida, mas com reuso de embeddings e model cache em RAM (<1ms). |
| `13-gate-memory-dream.md` | Gate para Extração de Memória | Sintaxe Python quebrada e debounce arbitrário de 3 turnos que descartava memórias importantes informadas no início da conversa. | Mantida a extração assíncrona em background via `extract_user_memory_background`. |
| `14-fusion-quorum-judge.md` | Fusion com Quorum e Juiz | Falácia lógica: usava `difflib.SequenceMatcher.ratio() >= 0.8` para medir concordância entre LLMs. Modelos diferentes expressam a mesma ideia com palavras diferentes, tornando similaridade de caracteres inútil. | Mantido o orquestrador do Fusion com juiz semântico ponderado. |
| `15-fusion-k-of-n-timeout.md` | Fusion K-of-N com Timeout | Algoritmo quebrado: usava `asyncio.wait(FIRST_COMPLETED)` cancelando os outros modelos antes de atingir K, e selecionava a resposta mais rápida usando `max(latency_ms)` (invertendo a lógica). | Mantido o modo Fusion original aguardando os modelos selecionados e consolidando via juiz. |
| `17-write-behind-pragmas.md` | Write-Behind e Pragmas | Incompatibilidade de esquema: colunas inexistentes (`requests_used`, `date`) na tabela `model_quota_status` e risco de perda de auditoria em reinicializações. | Adicionados PRAGMAs seguros (`busy_timeout=10000`, `synchronous=NORMAL`) no pool de conexões real. |
| `18-heuristics-aux-tasks.md` | Heurísticas para Tarefas Auxiliares | Diagnóstico incorreto: assumia que o NexusLocal chamava LLMs para títulos de chat e web search. O NexusLocal já utilizava heurísticas locais e slices de string. | Nenhuma mudança necessária; overhead de LLM para tarefas auxiliares já era zero. |
| `19-laya-head-budgeting.md` | Head Budgeting de 1500 caracteres | Prejudicial ao RAG e Cache: truncar cegamente textos para 1500 chars cega a busca vetorial em perguntas conceituais longas, degrada o recall de RAG de projetos e causa falsos-positivos de cache semântico. | Mantido embedding do texto integral da query, com compartilhamento canônico em RAM via `RequestContext`. |
| `20-laya-abstention-gating.md` | Abstention Gating & Confiança | Falácia estatística: tratava a confiança heurística do regex como probabilidade calibrada com limiar `0.72`, rebaixando injustamente perguntas profundas ou técnicas formuladas coloquialmente para `GENERAL_CHAT`. | Mantida a classificação determinística por sinais lexicais e momentum de tópico. |
| `21-laya-unicode-prefilter.md` | Pré-filtro Unicode & Densidade Sintática | Falsos positivos severos: densidade sintática de 12% classifica Markdown, tabelas, URLs e LaTeX como código. Detector de Unicode `ord(ch) > 0x024F` incluía símbolos, matemática e emojis em vez de scripts reais. | Mantidas as regexes pré-compiladas com limites de tamanho sem curtos-circuitos destrutivos. |
