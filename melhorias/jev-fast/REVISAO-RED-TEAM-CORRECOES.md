# Revisão corretiva JEV-Fast — 2026-10-13

Esta nota complementa os planos ativos depois da auditoria adversarial. Ela registra o que foi corrigido no código e as propostas que continuam bloqueadas por incompatibilidade, risco de regressão ou falta de calibração. Não autoriza deploy nem execução de migrações no banco de produção.

## Correções aplicadas no código

1. **Cache semântico escopado por usuário e estado de memória.** `CacheManager.get()` agora exige identidade de usuário; o fingerprint, a busca vetorial e a deduplicação filtram por `user_id`. A busca de similaridade também restringe candidatos ao mesmo `context_fingerprint`, evitando reutilizar uma resposta produzida com outra memória do mesmo usuário. A gravação não recua silenciosamente para uma linha sem escopo se a coluna nova não estiver disponível. A busca exata (`cache_exact`) preserva seu comportamento existente.
2. **Índice para o escopo do cache semântico.** `init_db()` cria o índice composto `(user_id, model_id, fingerprint)` depois da migração das colunas.
3. **Embeddings concorrentes por request.** `RequestContext` compartilha a tarefa em andamento para a mesma chave, evitando inferências duplicadas quando consumidores concorrentes pedirem o mesmo embedding.
4. **Model Cache com quota atual.** O catálogo/ranking continua em cache por 30 segundos, mas `model_quota_status` é consultado a cada seleção para não usar estado de quota expirado.
5. **Vision L1 limitado.** O cache em RAM agora usa LRU com limite de 512 entradas e expiração; a leitura de arquivo do relay foi movida para `asyncio.to_thread`.

## Planos que permanecem bloqueados

- **12 — paralelização:** os exemplos usam campos que não existem em `RequestContext` e não modelam as dependências entre memória, fingerprint e cache. Não paralelizar o pipeline até substituir os exemplos por chamadas reais com limites de concorrência e ownership claro das conexões SQLite.
- **15 — Fusion K-of-N:** o algoritmo atual espera `FIRST_COMPLETED`, não K respostas, e escolhe o maior tempo de resposta como se fosse o menor. Não integrar esse algoritmo. O Fusion atual continua com o comportamento existente.
- **16 — Token Bucket:** os limites atuais são aproximações estáticas; não há consumo atômico no envio nem coordenação entre workers. O filtro do Smart Router que só consultava disponibilidade foi removido: não representava rate limiting e poderia influenciar a afinidade sem reservar quota. A prevenção de 429 depende de integração com failover e limites validados.
- **19 — head budgeting:** não aplicar 1.500 caracteres ao embedding compartilhado por cache semântico e RAG. Hash integral não impede falsos hits na busca vetorial truncada. Qualquer orçamento futuro deve ter chave/perfil separado por consumidor e validação de recall.
- **20 — abstention gating:** não impor `0.72` como probabilidade; a confiança atual do classificador é heurística. Requer dados rotulados e calibração antes de rebaixar intenções.
- **21 — Unicode/sintaxe:** não classificar como código com base apenas em densidade de pontuação. Markdown, LaTeX, URLs e tabelas são falsos positivos previsíveis; Unicode deve ser detectado por script, não por `ord(ch) > 0x024F`.
- **08 e 09 — validação, recuperação e benchmark:** não inserir verificadores heurísticos ou escrita síncrona de benchmark no caminho de resposta sem critérios de aceitação, limite de retries e instrumentação assíncrona.

## Limitações conhecidas após as correções

- A tabela de cache semântico mantém linhas legadas com `user_id IS NULL`; as consultas semânticas agora as ignoram. Não há backfill nem limpeza automática dessas entradas.
- O Vision L1 ainda compartilha a chave persistente existente por `file_hash`. O banco não registra versão do prompt do relay, portanto uma alteração de prompt pode deixar descrições persistidas antigas elegíveis. Corrigir essa invalidação com precisão exige migração aditiva, integridade validada do banco ativo e planejamento de deploy.
- O Token Bucket não é uma garantia operacional de rate limiting até ser integrado ao despacho de chat, failover, Fusion e Vision Relay com limites confiáveis.
- Nenhum teste foi executado neste ajuste e nenhuma migração foi aplicada ao banco ativo.
