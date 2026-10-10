# 🧭 00. Smart Intent Router: Visão Geral, Motivação e Benchmarks
**Multi+ / NexusLocal** · Planejamento Arquitetural

---

## 1. Contexto e Diagnóstico do Problema

Atualmente no **Multi+ (NexusLocal)**, a seleção de modelos depende 100% de decisão humana ou de modos especiais pré-ativados:
1. **Sobrecarga Cognitiva (Fadiga de Escolha):** A cada pergunta, o usuário precisa decidir: *"Uso Groq Llama 3.3 70B? DeepSeek R1? Qwen 2.5 Coder? Gemini 2.5 Flash?"*.
2. **Desperdício de Cota e Latência em Tarefas Simples:** Enviar saudações, traduções pontuais ou perguntas triviais de sintaxe para modelos de 70B ou modelos de *Thinking* adiciona latência desnecessária (2 a 5 segundos de espera) e consome cotas diárias de provedores gratuitos ou pagos.
3. **Frustração em Tarefas Complexas:** O usuário esquece o seletor em um modelo leve (ex: Llama 3.1 8B) e pede uma refatoração arquitetural profunda de código ou uma demonstração matemática, obtendo respostas incompletas ou alucinações.
4. **O Modo Fusion não é a resposta universal:** O Fusion é excelente para síntese de alta complexidade, mas dispara 3 modelos em paralelo simultaneamente, o que é um exagero para 80% dos turnos cotidianos de chat.

### A Lacuna Atual
O sistema já possui um **módulo de ranking de alta precisão** ([`backend/ranking/scorer.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/scorer.py)) e uma **cascata de failover em 2 tiers** ([`backend/ranking/failover.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py)), mas ambos só atuam **depois** que o modelo já foi escolhido ou quando ele esgota sua cota.

Falta a **cabeça inteligente de entrada**: o **Auto-Roteador**.

---

## 2. O que é o Smart Intent Router?

O **Smart Intent Router** é um orquestrador preditivo ultrarrápido que avalia o prompt do usuário, os anexos presentes e o contexto da conversa antes do streaming. Ele classifica a necessidade real da tarefa e despacha a requisição para a IA mais adequada do ecossistema local e de nuvem.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Prompt / Pergunta do Usuário                    │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 1: Classificador de Intenção e Complexidade        │
│          (Heurísticas Léxicas + Sinais Estruturais · < 2ms)            │
│                                                                        │
│  • Análise sintática (código, fórmulas, tamanho, palavras-chave)       │
│  • Presença de anexos (imagem/PDF) ou busca web ativa                  │
│  • Extensão do contexto acumulado                                      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                  Classe Identificada + Nível de Complexidade
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 2: Seletor de Modelo Ótimo (Matriz de Políticas)   │
│                                                                        │
│  • Consulta model_quota_status (garante que modelo está disponível)    │
│  • Prioriza por NexusLocal Score do ranking na categoria da tarefa     │
│  • Aplica política ativa (ex: Econômico / Equilibrado / Pro)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                         Modelo Ideal Selecionado
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             ESTÁGIO 3: Execução com Rede de Segurança (Failover)       │
│                                                                        │
│  • Se o modelo roteado responder OK ➔ Transmissão imediata             │
│  • Se bater Rate Limit (429) ou Erro ➔ Cascata de Failover assume      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Benchmarks de Mercado e Lições Aprendidas

| Solução | Abordagem | Ponto Forte | Limitação / Risco | Como o NexusLocal fará melhor |
| :--- | :--- | :--- | :--- | :--- |
| **OpenRouter (`openrouter/auto`)** | Seleção dinâmica por custo e throughput médio | Simples para o cliente | Caixa-preta opaca; frequentemente escolhe modelos inesperados | **Transparência Total:** Notificação visual direta na mensagem informando por que aquele modelo foi escolhido. |
| **RouteLLM (LMSYS / Anyscale)** | Classificador binário treinado (Pequeno vs Grande) | Reduz custos de API em até 85% preservando 95% do MMLU | Requer treinamento supervisionado de embeddings e modelo local dedicado | **Pipeline em 2 estágios:** Heurísticas determinísticas instantâneas (< 2ms) com fallback semântico leve. |
| **Martian Model Router** | Teoria de mapas e roteamento token a token | Alta precisão teórica | Latência extra sensível em cada requisição | **Zero Latência Adicional:** A classificação ocorre antes do stream iniciar, sem chamadas de rede externas intermediárias. |
| **Claude / ChatGPT Dynamic Mode** | Roteamento automático interno (Haiku/Sonnet ou 4o-mini/o3) | Experiência sem atrito para o usuário comum | Preso ao ecossistema fechado de uma única empresa | **Multi-Provedor Aberto:** Conecta livremente Groq, OpenRouter, Cerebras, SambaNova, Ollama e Gemini. |

---

## 4. Princípios Inegociáveis de Design

1. **Zero Latência Extra (< 2ms):** A classificação da intenção **NÃO PODE** fazer uma chamada HTTP externa síncrona a uma LLM apenas para decidir qual LLM usar. Deve rodar 100% no servidor local (Python puro + regex compilado + sinais estruturais).
2. **Transparência Radical:** O usuário nunca deve se sentir enganado. Se a pergunta foi despachada para o `Llama 3.3 70B (Groq)` por ser código, a interface exibe um badge discreto: `🎯 Auto: Código & Engenharia`.
3. **Respeito à Liberdade do Usuário:** O modo `Auto` é uma opção a mais no topo do dropdown de modelos (`ModelSelector.tsx`). Se o usuário quiser fixar um modelo específico manualmente, o sistema obedece sem interferência.
4. **Simbiose com o Failover Existente:** O roteador inteligente seleciona o *melhor candidato de largada*; se ele falhar ou acusar cota esgotada, a infraestrutura já construída em [`backend/ranking/failover.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py) entra em ação automaticamente.
5. **Autonomia Financeira e de Cota:** Por padrão, perguntas simples usam provedores rápidos e gratuitos (`is_free = 1`), preservando cotas premium para tarefas analíticas reais.
