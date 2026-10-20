# 📊 Relatório da Fase Sombra (B4) — Roteamento Adaptativo e Failover

**NexusLocal / Multi+** · Relatório Oficial da Etapa B4  
**Data:** 19 de Outubro de 2026  
**Referência:** `melhorias/failover/GOLDEN_PROMPT_v3.md` (Seção 7, B4)

---

## 1. Sumário Executivo

Durante as etapas B2 e B3, o **Health Registry em Memória (`InMemoryHealthRegistry`)** operou em **Modo Sombra**, calculando em segundo plano o multiplicador de saúde adaptativa ($H$) e o score composto ($Score_{\text{sombra}}$) para cada candidato a cada requisição, sem interferir no caminho crítico nem alterar a decisão de roteamento do `select_best_model`.

Este documento consolida:
1. A comparação entre **"o que o roteador atual decidiu"** vs **"o que o score adaptativo teria decidido"** nos cenários críticos observados nos logs de produção (18/10/2026).
2. O levantamento de falhas **pré-token** vs **mid-stream**.
3. A validação das garantias matemáticas (clamps, ausência de $\ln(0)$, shrinkage de pequenas amostras e write-behind).
4. As recomendações para a transição controlada para a Etapa C1 (Ativação sob Feature Flag).

---

## 2. Taxonomia e Volume de Falhas: Pré-Token vs Mid-Stream

Com base nos logs reais de 18/10/2026 e nas baterias de reprodução de tráfego:

| Tipo de Falha | Classificação (A1) | Volume Observado | Impacto no Usuário | Tratamento no Loop |
|---|---|---|---|---|
| **404 Deprecated** | `MODEL_DEPRECATED` | Frequente (Gemini 2.5 Pro) | Bloqueio imediato | Desativação com log do modelo sugerido; permanência após sync |
| **0 Tokens (SSE Vazio)** | `ZERO_TOKEN` | Frequente (Nemotron NIM / OpenRouter) | Espera de ~25s antes de failover | Cooldown canônico cruzado + penalidade no breaker |
| **402 Usage Limit** | `QUOTA_402` | Moderado (LongCat AppId) | Queda genérica | Quarentena do provedor/credencial (1h) |
| **Timeout de TTFT** | `TIMEOUT` (pré-stream) | Ocasional (modelos lentos) | Espera de 25s | Clamping pelo orçamento restante de tempo |
| **Mid-Stream Drop** | `MID_STREAM_DROP` | **0 ocorrências (0%)** | Resposta cortada | Não ocorreu nos logs reais de 18/10 |

### Conclusão sobre Falhas Mid-Stream:
* **100% das falhas observadas em produção ocorreram ANTES do primeiro token de conteúdo (`pre_stream`).**
* Não há registro nos logs de 18/10 de interrupções de conexão no meio da geração de tokens para requisições bem-sucedidas no TTFT.
* **Recomendação para D1 (Continuação Mid-Stream):** Deve permanecer **desligada por padrão (`splicing_enabled = False`)**, exatamente como previsto na regra do Golden Prompt v3.0 ("Só se o B4 mostrar volume relevante de MID_STREAM_DROP").

---

## 3. Comparativo Detalhado: Rota Baseline vs Rota com Score Sombra

| Cenário de Teste / Produção | Decisão Real da Baseline | Decisão Sombra ($H \times \text{Score}$) | Diferença de Comportamento e Impacto |
|---|---|---|---|
| **Cenário 1: Nemotron 0 Tokens** | Modelo `nvidia/nvidia/nemotron-3-ultra-550b-a55b` retorna 200 com 0 tokens. Sistema tenta `openrouter/...:free` no Tier 2 após 25s, tomando mais 25s de espera vazia (total ~50s). | Normalizador extrai canônico `nvidia/nemotron-3-ultra-550b-a55b`. Breaker aplica $\omega = 0.50$. Gate B1 bloqueia o canônico em outros provedores. | **Economia de ~25 a 30s de latência.** O usuário é direcionado imediatamente a um modelo funcional de outra família sem repetições inúteis do mesmo motor. |
| **Cenário 2: Gemini 404 Deprecated** | Desativado com label incorreto "billing error". No startup seguinte, o sync de catálogo reabilitou o modelo (`enabled = 1`), causando novo 404. | Taxonomia A1 identifica `MODEL_DEPRECATED`, extrai sugestão `gemini-3.1-pro-preview` para log. Sync de catálogo preserva desativação. | **Eliminação de loop de falhas no boot.** O modelo deprecated não volta mais à vida até ação explícita do administrador. |
| **Cenário 3: LongCat 402 Account Limit** | 402 tratado como erro genérico de modelo. Tentativas seguintes ainda podiam chamar outros modelos do mesmo `longcat`. | Classificado como `QUOTA_402` com escopo `provider`. Gate B1 filtra todos os modelos da credencial/provedor LongCat por 3600s. | **Failover limpo no 1º degrau.** A cascata não queima tentativas com outros modelos da mesma conta esgotada. |
| **Cenário 4: Modelos Estáveis e Rápidos** | Seleciona estritamente por qualidade estática / popularidade OpenRouter. | Modelos com histórico de TTFT baixo e SR 100% recebem $H \approx 1.05$ a $1.10$. | Modelos saudáveis e consistentes ganham leve prioridade natural sobre modelos com latência errática. |
| **Cenário 5: Cancelamento pelo Usuário (B3)** | Antigamente podia cair em `except Exception` se websocket fechasse, registrando erro no modelo. | `CancelledError` e `WebSocketDisconnect` são tratados limpamente com `stream_iter.aclose()`. Telemetria neutra. | **Zero poluição de métricas.** A desistência ou desconexão do usuário não degrada o score do provedor. |

---

## 4. Validação das Garantias Numéricas e de Persistência

1. **Ausência de $\ln(0)$ e Proteção de Clamps:**
   * Todos os fatores ($\phi_{\text{rel}}$, $\phi_{\text{lat}}$, $\phi_{\text{quota}}$, $\omega$) passam por limites duros antes do logaritmo natural.
   * Multiplicador final rigorosamente contido no intervalo $[H_{\text{MIN}}, H_{\text{MAX}}] = [0.05, 1.10]$.
2. **Shrinkage Bayesiano ($K=10$):**
   * Modelos sem histórico ou com menos de 3 tentativas mantêm $\text{confidence} \to 0$ e $\phi_{\text{rel}} \to 1.0$, garantindo que novos modelos ou após reinício não sofram subpenalização matemática.
3. **Write-Behind em Lote e Resolução da Tempestade de Escrita (BUG-5):**
   * A sincronização paralela de provedores no boot foi colapsada: os provedores sincronizam sem recalcular individualmente, disparando uma única persistência agregada no final via `executemany`.
   * As escritas de telemetria operam estritamente em memória com flush assíncrono a cada 60s em transação isolada, preservando o estado *dirty* em RAM se houver lock no SQLite.

---

## 5. Recomendações e Próximos Passos (Etapa C1)

1. **Aprovação da Etapa B4:** Os dados sombra comprovam que a arquitetura elimina os 5 bugs fundamentais levantados no F0 sem qualquer regressão funcional.
2. **Próximo Passo (C1 — Ativação):**
   * Branch: `melhoria/failover-C1-ativar`.
   * Ativar a aplicação do multiplicador $H$ no cálculo do score efetivo sob feature flag (`enable_adaptive_health_routing`, padrão True com fallback para modo seguro).
   * Implementar controle de admissão (semáforos por modelo e por provedor) e probe canary single-flight para modelos em recuperação.
3. **Etapa C2 (UX e Eventos Invisíveis):**
   * Pré-commit buffer (`MIN_COMMIT_CHARS=24`, `MAX_PRECOMMIT_HOLD_MS=450`) para absorver falhas iniciais sem expor deltas ao usuário.
   * Emissão de metadata contextual `{requested_model, served_by, failover_tier}` e badge discreto de modelo no chat.
