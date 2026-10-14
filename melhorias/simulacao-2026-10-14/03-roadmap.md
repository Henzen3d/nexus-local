# Roadmap priorizado — impacto ÷ esforço

Estimativas de implementação + teste dirigido, **não compromissos de prazo**. Impacto: 1–5, considerando bloqueio, confiabilidade, privacidade e alcance. Esforço em horas de engenharia; razão = impacto / ponto médio. Ordenação dentro de cada faixa usa essa razão. Itens de risco alto funcionam como **gates de release**, mesmo quando uma correção cosmética tem razão maior. Não inclui tempo de decisão de produto nem homologação em dispositivos reais.

## Gates antes de recomendar o produto a novos usuários

- **P0 confiabilidade:** primeiro uso funcional, Ollama sem chave, scope de cache seguro, Judge preservando fontes e Fusion multimodal sem TypeError.
- **P0 controle/privacidade:** cancelar de verdade, remover tokens dos logs, corrigir promessa de memória, política por destino.
- **P1 uso diário:** acessibilidade, limites, estados degradados, configurações transacionais e recuperação de upload/rede.
- Os itens abaixo são propostas. Nenhuma dessas correções foi aplicada ao código de produto nesta auditoria.

## Quick wins — cada item <1 h

| Ordem | Item / IDs | Impacto | Horas | Razão | Critério de aceite testável |
|---:|---|---:|---:|---:|---|
| Q1 | Condicionar Authorization em compatível local — B02 | 5 | 0,25–0,75 | 10 | Ollama sem chave envia request sem header Authorization e conclui stream; provedor que exige chave continua recusando ausência |
| Q2 | Substituir promessa absoluta de memória — U07 | 5 | 0,25–0,75 | 10 | Texto em todos os locales diferencia armazenamento local de transmissão ao provedor; testes de string não encontram “sem enviar memória para a nuvem” |
| Q3 | Corrigir chave `chat.generationError` e fallback — U02 | 3 | 0,25–0,5 | 8 | Forçar erro em PT/EN/ES; nenhum identificador i18n aparece no DOM; título e ação explicam falha |
| Q4 | Mitigação segura: bypass semântico com contexto não coberto — B03 | 5 | 0,5–0,9 | 7,1 | Projeto/anexos/web/contexto mutável dão miss até scope completo; user isolation/follow-up continuam passando |
| Q5 | Documentar comando correto, JWT e bootstrap — B01/U01 | 5 | 0,5–0,9 | 7,1 | Revisor segue README em ambiente limpo e obtém health+login sem inferir PYTHONPATH ou senha; launcher definitivo fica em M2 |
| Q6 | Fazer sufixo Fusion aceitar lista multimodal — B07 | 5 | 0,5–0,9 | 7,1 | Proposers recebem imagem e part textual de autocrítica; entrada original permanece imutável; nenhum list+str |
| Q7 | Restaurar contexto ao compor system do Judge — B06 | 5 | 0,5–0,9 | 7,1 | Captura do Judge contém regra e fonte-canário do projeto além do papel de juiz; orçamento definitivo em M5 |
| Q8 | Validar envelope WS antes de `.get/.strip` — B09 | 4 | 0,5–0,9 | 5,7 | `[]`, `null`, número e mensagem não-string devolvem erro recuperável; ping seguinte funciona |
| Q9 | Adicionar proxy de anexos ao dev — B01 | 3 | 0,5–0,75 | 4,8 | URL relativa assinada responde imagem/arquivo, não index.html; expirada responde 403; Docker não regrede |
| Q10 | Labels de botões/selects e controles de perfil não aninhados — U03 | 3 | 0,5–0,9 | 4,3 | Axe não acusa button-name/select-name/nested-interactive nas telas inventariadas |
| Q11 | Estado terminal no card Fusion — U08 | 3 | 0,5–0,9 | 4,3 | Após stream_end, card mostra “Concluído” e modelo do Judge; não fica consolidando |

**Cuidado com a categoria:** Q4 é mitigação, não solução completa de cache. Q2 corrige comunicação, não implementa consentimento granular. Q7 não resolve orçamento. Redação de logs em todos os processos e cancelamento real não são prometidos em <1 h.

## Médio prazo — entregas pequenas verificáveis

| Ordem | Item / IDs | Impacto | Horas | Razão | Critério de aceite testável |
|---:|---|---:|---:|---:|---|
| M1 | UTC uniforme, UPSERT/unique e renovação de cache — B04 | 4 | 2–4 | 1,33 | Relógio congelado: 71/72 h hit, 73/72 miss; refresh muda resposta e timestamp; duas inserções concorrentes deixam uma linha |
| M2 | Smoke de bootstrap/launcher e readiness — B01/U01 | 5 | 3–5 | 1,25 | Checkout limpo instala conjunto único de deps, gera/configura segredo com segurança, cria admin explicitamente e valida processos antes de anunciar sucesso |
| M3 | Configuração Fusion atômica e validação de diversidade — B15 | 3 | 2–3 | 1,2 | Config inválida retorna 422 e mantém juiz+participantes anteriores intactos; IDs modelo/provedor coerentes; regra de mesmo provedor documentada |
| M4 | Remover bearer da URL e sanitizar logs — B13 | 5 | 4–6 | 1,0 | Ticket único curto expira e não se reutiliza; varredura de access/app/proxy logs não encontra JWT/chave; Origin hostil rejeitado no browser handshake |
| M5 | Budget por destino, input gigante e failover — B08 | 5 | 4–8 | 0,83 | Somatório input+completion nunca supera janela do modelo da tentativa; 100k CJK em modelo 8k dá erro antes do provider; Judge com 3 respostas longas cabe |
| M6 | Erros semânticos e estados de web/configuração — U02/U08 | 3 | 3–5 | 0,75 | Ausência de chave não aparece como quota esgotada; empty/failed/success da busca são distintos; erro possui ação e não duplica toasts |
| M7 | Cache com scope/revisão completos — B03 | 5 | 6–8 | 0,71 | Matriz projeto/documento/system/anexo/memória/ferramenta/usuário mostra miss em mudanças; hit apenas para contexto elegível; semântico false-positive corpus definido |
| M8 | Foco mobile, contraste e 44 px — U03/U04 | 4 | 4–8 | 0,67 | Tab não entra em sidebar oculta; menu semanticamente válido; axe sem falhas inventariadas; targets medidos ≥44×44; foco retorna ao invocador |
| M9 | RAG degradado + lexical independente + retry — B05 | 5 | 6–10 | 0,63 | Com download bloqueado, UI avisa degradação e pergunta sem “arquivo” recupera sentinel; reativar embedder reindexa; zero vetores não aparece vector_ready |
| M10 | Normalizar uploads/limites/cleanup — B12 | 4 | 5–8 | 0,62 | Vazio/tipo falso/PDF truncado/26 MiB recebem respostas previsíveis; limite interrompe leitura incremental; nenhum raw file órfão após erro |
| M11 | Recuperar saúde da suíte/i18n — evidências de 04-testes | 3 | 4–6 | 0,6 | Suite determinística offline sem fixture ausente ou tabela inexistente; integração MiniLM marcada/isolada; nenhuma chave usada em t() ausente |
| M12 | Turn lifecycle: idempotência + cancelamento + rascunho — B10/B11/U06 | 5 | 8–12 | 0,5 | Dois frames com mesmo request_id = uma geração; Parar cancela provider em prazo definido, parcial persiste; eventos antigos ignorados; envio não aceito preserva rascunho |
| M13 | Logs JSON, correlação e métricas — B16 | 3 | 5–8 | 0,46 | Um turn_id correlaciona WS/cache/RAG/provedores/SQLite sem texto privado; mede TTFT, tokens descartados e fim de persistência |
| M14 | Lazy-loading e tokens visuais/fontes offline — U09 | 3 | 6–10 | 0,38 | Painéis admin/relatórios não entram no JS inicial; medir baseline/progresso do gzip; cores seguem contrato revisado; UI funciona com Google Fonts bloqueado |
| M15 | Memória por destino e chaves protegidas — B14/U07 | 5 | 10–16 | 0,38 | Proposer remoto não recebe canário local-only mesmo quando selecionado Ollama; backup SQLite sem master key não revela segredo; migração é reversível e testada |

## Apostas maiores — medir antes de ampliar arquitetura

| Ordem | Entrega / IDs | Impacto | Horas | Razão | Critério de aceite / experimento |
|---:|---|---:|---:|---:|---|
| A1 | Busca full-text e variantes editar/regenerar — U05 | 4 | 16–24 | 0,2 | Termo no meio de mensagem acha conversa e snippet; editar cria branch sem perder anterior; regenerar tem variante/autor/modelo/custo; owner check em todas as operações |
| A2 | RAG rastreável + reranking — B05/B17 | 5 | 24–40 | 0,16 | Dataset PT/EN com fatos início/meio/fim; comparar recall@k e precisão de citações contra baseline híbrido; cada citação abre chunk/página/revisão; fonte adversarial não aciona ferramentas |
| A3 | Fusion adaptativo por qualidade/custo — B06/B08 + análise de viés | 4 | 24–40 | 0,13 | Avaliação cega em permutações/longitudes; medir ganho vs melhor modelo único, custo e p95; deadline/quorum/resultado parcial explicitamente aprovados |
| A4 | Escala: índice vetorial/FTS e fila durável — B16 | 4 | 24–48 | 0,11 | Benchmark 1k/10k/100k chunks/cache; meta de p95 definida antes; recovery após kill/restart reprocessa pending; carga não causa locks ou perda de turno |
| A5 | Compactação recuperável de conversas — B08 | 4 | 24–48 | 0,11 | Conversa longa conserva fatos-canário com resumo versionado, permite inspecionar omissões e recuperar fonte; não sobrescreve histórico bruto |

## Dependências e sequência sugerida

1. Executar quick wins que mitigam bloqueio e incorreção; Q4 pode desativar cache semântico em contextos de risco imediatamente.
2. Fixar contrato de turno (M12) antes de implementar variantes/reconexão sofisticadas (A1). Um `turn_id` único também alimenta M13.
3. M5 antes de expandir quantidade de modelos do Fusion. M9 antes de medir ganho de reranker. M7 antes de reativar cache amplo.
4. Acordar decisões pendentes em `00-resumo.md`; não remover restrições/políticas por conveniência técnica.
5. Aceite de release inclui build, suite offline, fluxo primeiro uso e screenshots desktop/mobile, não somente teste unitário.
