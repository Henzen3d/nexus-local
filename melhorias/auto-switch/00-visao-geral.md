# 🧭 00. Visão Geral: Motor de Auto-Failover, Desativação e Resiliência Dinâmica
**NexusLocal / Multi+** · Documento Mestre de Funcionalidades e Melhorias

---

## 1. O Diagnóstico do Teste Prático

Em testes reais de uso no ambiente de produção (`multi.mob.tec.br`), o usuário selecionou o provedor **LLM7.io** e iniciou uma sequência de testes enviando a mensagem simples `"oi"`:

```
[Usuário]: oi
  ├─ ❌ Minimax M3 (LLM7.io) ➔ Erro 402: "Insufficient balance. Please top up your balance to continue."
  │     └─ Efeito na tela: Card vermelho 'chat.generationError'. Conversa travada.
  │
  ├─ ❌ Minimax 2.7 (LLM7.io) ➔ Erro 400: "Model 'minimax-m2.7' is currently unavailable."
  │     └─ Efeito na tela: Card vermelho 'chat.generationError'. Conversa travada.
  │
  └─ ✅ GPT Oss:20b (LLM7.io) ➔ Resposta 200 OK: "Bom dia, Osmar!"
        └─ Efeito na tela: Resposta exibida normalmente após 3 tentativas manuais.
```

### Quadro Comparativo do Teste

| Modelo Testado | Código de Erro | Mensagem do Provedor | Diagnóstico Técnico | Ação Ideal do Sistema |
| :--- | :--- | :--- | :--- | :--- |
| **Minimax M3** | **HTTP 402** | `"Insufficient balance. Please top up your balance to continue."` (`insufficient_quota` / `insufficient_balance`) | **Erro Estrutural de Saldo:** A chave gratuita da LLM7.io não dá acesso a esse modelo sem recarga de saldo pago. | **Desativação Permanente** (`enabled = 0`, `confirmed_free = 0`) para sumir da lista e não poluir o seletor. **Pular imediatamente** para o próximo modelo. |
| **Minimax 2.7** | **HTTP 400** | `"Model 'minimax-m2.7' is currently unavailable."` (`invalid_request_error` / `model_unavailable`) | **Indisponibilidade Temporária:** A instância do modelo está reiniciando, em manutenção ou temporariamente sem nós computacionais. | **Manter Ativo** no provedor, mas registrar em **Cooldown Temporário (ex: 10 min)** na tabela `model_quota_status`. **Pular imediatamente** para o próximo modelo. |
| **GPT Oss:20b** | **HTTP 200** | *Resposta normal* | **Modelo Saudável e Operacional:** Totalmente funcional e com capacidade de atendimento. | **Gerar a resposta**, notificar sutilmente a transição e **sincronizar o seletor** do chat para ele. |

---

## 2. A Causa Raiz: Por que o Sistema Travou em vez de Pular Sozinho?

Investigando o pipeline de orquestração em [resolve_request.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L165-L206):

```python
# Trecho atual do backend:
try:
    async for token in provider.stream_chat(model=model_name, messages=history):
        ...
except RateLimitError as e:
    # ÚNICO erro que mantinha o loop de failover vivo!
    await mark_model_exhausted(current_model_id, db, e.retry_after, str(e))
    continue
except Exception as e:
    # Qualquer outro erro (HTTP 402, 400, 503, 500) caía aqui:
    await ws.send_json({
        "type": "error",
        "message": f"Erro ao chamar modelo: {error_msg}",
    })
    # Abortava imediatamente!
    return None
```

### O Gargalo Arquitetural Identificado:
1. **Tratamento Restrito de Exceções:** Apenas `RateLimitError` (HTTP 429) permitia avançar no loop `while attempt < _MAX_FAILOVER_ATTEMPTS`.
2. **Abort Imediato em Erros HTTP:** Erros como 402 ou 400 levantavam `RuntimeError` em [base.py](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L101), caindo no bloco `except Exception`, que disparava um card vermelho para o usuário e encerrava o stream com `return None`.
3. **Ausência de Prioridade do Mesmo Provedor (Tier 0):** O motor de failover em [failover.py](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py) só conhecia duas etapas:
   - *Tier 1:* Irmãos da mesma família (ex: `deepseek-r1` em outros provedores). Como `minimax-m3` não pertence a nenhuma família cadastrada, o Tier 1 era ignorado.
   - *Tier 2:* Ranking geral global (podendo desviar para outro provedor qualquer, como Groq ou Gemini).  
   **Faltava o Tier 0:** Tentar os outros modelos disponíveis **do mesmo provedor** que o usuário escolheu (`LLM7.io`).

---

## 3. Os Quatro Pilares da Nova Solução

```
                    ┌──────────────────────────────────────────────┐
                    │      Requisição do Usuário (Prompt)          │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │      Execução da Chamada no Provedor         │
                    └──────────────────────┬───────────────────────┘
                                           │
                        ┌──────────────────┴──────────────────┐
                        │                                     │
                 Sucesso (HTTP 200)                      Falha de Chamada
                        │                                     │
                        ▼                                     ▼
             Stream de Tokens Normal               ┌──────────────────────┐
                        │                          │ Classificador de     │
                        ▼                          │ Erros Especializado  │
             Finalização Concluída                 └──────────┬───────────┘
                                                              │
                       ┌──────────────────────────────────────┴──────────────────────────┐
                       │                                                                 │
                       ▼                                                                 ▼
           [Erro Fatal: 402 / 404 / Sem Cota]                         [Erro Temporário: 400 / 503 / 429]
                       │                                                                 │
           • UPDATE models SET enabled = 0                            • Cooldown temporário (10 min)
           • Remove do seletor em tempo real                          • Mantém modelo ativado
           • Log de telemetria                                        • Evita chamá-lo nos próximos minutos
                       │                                                                 │
                       └──────────────────────────────┬──────────────────────────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │    Cascata de Auto-Switch    │
                                       │                              │
                                       │ Tier 0: Mesmo Provedor       │
                                       │ Tier 1: Mesma Família        │
                                       │ Tier 2: Ranking Global       │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
                                       ┌──────────────────────────────┐
                                       │ Próximo Modelo Conectado!    │
                                       │ • Badge sutil na mensagem    │
                                       │ • Seletor auto-sincronizado  │
                                       │ • Zero cards vermelhos       │
                                       └──────────────────────────────┘
```

### Pilar 1: Classificador Inteligente de Erros (Fatal vs. Temporário)
* **Erros Fatais (402, 404, invalid_model, insufficient_quota):** Desligam o modelo da lista permanentemente (`enabled = 0`).
* **Erros Temporários (400 unavailable, 503, 502, 429 rate limit):** Mantêm o modelo ativado no cadastro, mas aplicam um *cooldown* de 10 a 15 minutos na tabela `model_quota_status`.

### Pilar 2: Cascata de Transbordo com Prioridade Local (Tier 0)
Se o usuário escolheu o provedor `LLM7.io`, a contingência busca primeiro **outro modelo ativo e disponível dentro do próprio LLM7.io** (ex: `gpt-5.4-mini`, `gpt-oss-20b`). Apenas se todos os modelos do provedor falharem, o transbordo escala para outros provedores.

### Pilar 3: Continuidade Transparente no Chat (Zero Interrupção)
Em vez de abortar o WebSocket no primeiro erro, o backend:
1. Registra a falha do modelo atual;
2. Limpa o buffer de tokens;
3. Instancia o próximo modelo da fila;
4. Inicia o streaming para o usuário sem que ele perceba que houve uma falha interna.

### Pilar 4: Experiência Visual Sem Fricção (UI/UX)
* **Badge de Transição:** A resposta traz um aviso discreto:  
  `🔄 Alternado de Minimax M3 (saldo indisponível) → GPT Oss:20b`
* **Auto-Sincronização do Seletor:** O seletor de modelos na barra superior e no rodapé do chat atualiza automaticamente para o modelo que respondeu, preparando a próxima mensagem para fluir sem erros.

---

## 4. Melhorias e Recursos Adicionais para Reduzir Atrito

### ✦ 1. Ferramenta de Diagnóstico Rápido de Provedor em 1 Clique
No painel de administração ([AdminPanel.tsx](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/AdminPanel.tsx)), cada provedor ganha um botão **"🔍 Diagnosticar Modelos"**:
* O backend executa requisições de teste assíncronas em lote (1 token, prompt de ping) para todos os modelos daquele provedor em paralelo.
* Modelos que retornarem 402 ou 404 são desativados de antemão de forma automática.
* O usuário ganha a certeza de que todos os modelos visíveis no seletor estão 100% saudáveis.

### ✦ 2. Indicadores de Saúde no Dropdown de Modelos
O dropdown de modelos do chat passa a exibir pequenos sinais visuais:
* 🟢 **Ponto Verde:** Modelo verificado e respondendo com sucesso recentemente.
* 🟡 **Ponto Amarelo:** Em cooldown temporário (com dica visual: *"Indisponível temporariamente - liberando em X min"*).
* Modelos com 402 desativados ficam ocultos por padrão, com opção de visualização para administradores.

### ✦ 3. Fallback por Afinidade / Categoria
Se o modelo original era especializado em código (ex: `Codestral` ou `Qwen 2.5 Coder`) e falhar, o auto-switch prioriza modelos da mesma categoria técnica antes de recorrer a assistentes generalistas.

---

## 5. Comparativo da Experiência: Antes vs. Depois

| Aspecto | Antes (Comportamento Atual) | Depois (Com Auto-Switch) |
| :--- | :--- | :--- |
| **Tentativas para falar no chat** | 3 envios de mensagem manuais (`oi`, `oi`, `oi`) | **1 único envio.** O sistema resolve as falhas silenciosamente. |
| **Feedback na Interface** | 2 cards vermelhos de erro fatal bloqueando a tela | **Zero cards vermelhos.** Mensagem fluida com badge informativo discreto. |
| **Modelos que exigem saldo pago (402)** | Continuam ativos na lista, causando novos erros no futuro | **Desativados automaticamente** logo na primeira tentativa. |
| **Modelos em manutenção temporária (400)** | Bloqueiam o chat e confundem o usuário | **Entram em cooldown temporário** de 10 min e voltam sozinhos quando a infraestrutura restabelecer. |
| **Seletor de Modelos após o Erro** | Continua apontando para o modelo quebrado | **Atualiza automaticamente** para o modelo funcional que gerou a resposta. |
| **Esforço cognitivo do usuário** | Alto: pesquisar na documentação, abrir painel, desmarcar chaves | **Zero:** o NexusLocal se auto-gerencia e se auto-cura em tempo real. |
