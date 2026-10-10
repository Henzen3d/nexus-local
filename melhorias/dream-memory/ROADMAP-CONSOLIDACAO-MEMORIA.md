# 🗺️ Roadmap Mestre de Consolidação, Integridade e Otimização de Memória

> **Projeto:** NexusLocal — Dream Memory Consolidator 2.0  
> **Localização:** `melhorias/dream-memory/ROADMAP-CONSOLIDACAO-MEMORIA.md`  
> **Status Geral:** Planejamento Concluído — Pronto para Execução Faseada  
> **Data:** 10 de Outubro de 2026  

---

## 1. Visão Executiva

Este roadmap consolida o plano estratégico completo para transformar o sistema de memória do **NexusLocal** na solução mais avançada, resiliente e privativa do ecossistema de assistentes de IA, superando os gargalos conhecidos de soluções fechadas como ChatGPT Memory e Claude Projects.

### Princípios Inegociáveis:
1. **Armazenamento sem Limites Artificiais:** Não descartar dados úteis por tetos de 200 ou 500 fatos; o SQLite armazena dezenas de milhares de memórias com consumo desprezível de disco.
2. **Zero Degradação no Chat:** Recuperação ultrarrápida ($< 20\text{ms}$) combinando **FTS5 (BM25)** e **Similaridade Vetorial (FastEmbed)** com decaimento temporal.
3. **Fidelidade e Anti-Alucinação:** Proibição de "summarization smear" (perda de nuances contextuais), preservação rigorosa de fatos biográficos antigos e isolamento absoluto de entidades (usuário vs família vs projetos).
4. **Resiliência Absoluta:** Locks unificados, SQLite em modo WAL com timeout de 10s, snapshots SHA-256 e reversão em 1 clique.

---

## 2. Índice de Documentos e Fases

| Documento | Fase / Tema | Foco Principal | Status |
| :--- | :--- | :--- | :--- |
| [`00-visao-geral.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/00-visao-geral.md) | **Arquitetura Base** | Diagnóstico inicial e aprovação do Dream Consolidator. | Concluído (Referência) |
| [`06-auditoria-falhas-vulnerabilidades-online.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/06-auditoria-falhas-vulnerabilidades-online.md) | **Fase 0: Auditoria Crítica** | Mapeamento dos 10 gargalos do código atual e patologias de mercado (ChatGPT, Claude, Mem0). | Concluído |
| [`07-plano-blindagem-concorrencia-e-integridade.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/07-plano-blindagem-concorrencia-e-integridade.md) | **Fase 1: Concorrência & Locks** | Lock global `_memory_pipeline_lock` nas rotas manuais, SQLite WAL, sync atômico e fix no Pytest. | Pronto para Execução |
| [`08-plano-antiamnesia-clustering-e-semantica.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/08-plano-antiamnesia-clustering-e-semantica.md) | **Fase 2: Inteligência Semântica** | Clustering semântico pré-lote, blindagem de fatos >90 dias, anti-smear de nuances e barreira de família. | Pronto para Execução |
| [`09-plano-escala-desempenho-e-retrieval-infinito.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/09-plano-escala-desempenho-e-retrieval-infinito.md) | **Fase 3: Escala & Retrieval Híbrido** | Remoção de limites de 200/500 fatos, motor de busca FTS5 BM25 + Vetorial e otimização matricial NumPy. | Pronto para Execução |
| [`10-plano-seguranca-pii-e-experiencia-ui.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/10-plano-seguranca-pii-e-experiencia-ui.md) | **Fase 4: Segurança & Experiência UI** | Redator de chaves/senhas, visualização de linhagem/diff no frontend e desambiguação assistida. | Pronto para Execução |

---

## 3. Checklist Consolidado de Execução

### Fase 1: Concorrência e Estabilidade Estrutural (Prioridade Máxima)
- [ ] Centralizar `memory_pipeline_lock` para proteger rotas manuais (`dream_run_now` e `dream_preview`).
- [ ] Padronizar conexões SQLite em `memory_dream.py` com `PRAGMA busy_timeout = 10000;` e `WAL`.
- [ ] Implementar cláusula otimista `WHERE is_active = 1` para não alterar fatos modificados durante a inferência.
- [ ] Corrigir fixtures assíncronos em `backend/tests/test_dream_edge_cases.py` para 100% de aprovação no `pytest`.

### Fase 2: Inteligência Semântica e Anti-Amnésia
- [ ] Substituir o fatiamento sequencial cego por **Clustering Semântico em 2 Níveis** (Escopo + Cosseno).
- [ ] Atualizar System Prompt para proibir arquivamento automático de fatos biográficos permanentes com mais de 90 dias.
- [ ] Adicionar regra inegociável de preservação de nuances condicionais ("quando X faça Y").
- [ ] Implementar barreira determinística por código em `verify_dream_safety` para impedir vazamento de fatos familiares (`family.*`) ou de projetos para o perfil pessoal do titular.
- [ ] Adicionar checagem de novidade lexical para prevenir alucinação cascata de novos substantivos.

### Fase 3: Escala Ilimitada e Busca Híbrida de Alta Performance
- [ ] Remover permanentemente a deleção automática de memórias ao atingir 200 fatos em `add_memory_fact`.
- [ ] Remover limite fixo de 500 fatos, habilitando consolidação por ondas sem perda de dados.
- [ ] Criar tabela virtual SQLite `user_memory_fts` (FTS5) para buscas literais ultrarrápidas.
- [ ] Implementar algoritmo híbrido no chat: $Score = 0.50 \cdot Vetor + 0.30 \cdot BM25 + 0.20 \cdot RecencyDecay$.
- [ ] Otimizar produto interno de vetores via multiplicação matricial NumPy em C.

### Fase 4: Segurança, Auditoria na UI e Desambiguação Ativa
- [ ] Criar sanitizador de expressões regulares para detectar e ofuscar API keys, senhas e tokens JWT.
- [ ] Adicionar indicador visual de linhagem histórica de cada fato consolidado no `UserMemoryPanel.tsx`.
- [ ] Melhorar o modal de Diff no `DreamJournalSection.tsx` com visualização de cores estilo Git Diff.
- [ ] Implementar fila de desambiguação ativa com confirmação em 1 clique para contradições com alta incerteza.
- [ ] Criar ferramenta de exportação completa do cérebro de memórias em JSON/Markdown para backup do usuário.

---

## 4. Matriz de Arquivos Impactados

```
backend/
├── main.py                     # Unificação do lock de concorrência e remoção de limit=200 no loop periódico
├── database.py                 # Remoção do cap de 200 fatos, tabela FTS5, busca híbrida e helper SQLite resiliente
├── memory_dream.py             # Clustering semântico, novas regras de prompt, validação de entidades e batches em ondas
├── memory.py                   # Sanitizador de dados sensíveis (PII/secrets) e injeção estruturada no system prompt
├── routers/memory.py           # Proteção com lock em dream-run-now/preview e novos endpoints de exportação/filas
└── tests/
    ├── test_dream_edge_cases.py# Ajuste dos fixtures assíncronos do pytest e novos testes de concorrência
    └── test_dream_clustering.py# Novos testes unitários para o clustering semântico

frontend/src/
├── components/
│   ├── UserMemoryPanel.tsx     # Badges de linhagem de fatos, abas de status (ativos/arquivados) e perguntas de desambiguação
│   └── DreamJournalSection.tsx # Diff visual colorido no relatório de simulação e métricas de clusters
└── lib/
    └── dreamLog.ts             # Tipagem expandida com clusters e novos estados de auditoria
```

---

## 5. Próximos Passos Recomendados

Como solicitado, **nenhum código foi modificado nesta etapa**, preservando a estabilidade atual.  
Para iniciar a implementação prática, recomenda-se executar as fases sequencialmente começando pela **Fase 1 (Blindagem de Concorrência e Estabilidade)**, assegurando que os testes do Pytest passem e o SQLite esteja 100% blindado contra conflitos.
