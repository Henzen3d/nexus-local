# Esforço de raciocínio — Multi+ (NexusLocal)

Seletor de esforço no cockpit de modelos. Só aparece quando o modelo aceita um controle de quanto pensar. Não é um slider global.

**Status:** plano. Nenhum código de produto foi alterado por esta pasta.

Benchmark visual já capturado em `melhorias/new-chat-input/selecao-esforco.jpg` (flyout Claude: Baixo, Médio, Alto, Extra, Máx). Aquela imagem é referência de UX. Não é especificação de API.

## O que isto não é

- Não é o accordion de pensamento (`reasoning_content`, `<think>`). Isso já existe e só lê a resposta.
- Não é a temperatura do Smart Router. Temperatura e esforço são eixos diferentes.
- Não é ligar `reasoning_effort` em todo modelo do catálogo. Campo desconhecido costuma voltar HTTP 400 e quebrar o turno.

## Índice

1. [00-visao-e-diagnostico.md](00-visao-e-diagnostico.md) — o que o código faz hoje e por que reasoning ≠ esforço.
2. [01-taxonomia-de-controles.md](01-taxonomia-de-controles.md) — tipos de controle, níveis visíveis e mapa de famílias.
3. [02-backend-catalogo-e-payload.md](02-backend-catalogo-e-payload.md) — colunas, tradução por provedor, failover e o que fica de fora.
4. [03-interface-cockpit.md](03-interface-cockpit.md) — onde o seletor entra no balão já existente.
5. [04-roadmap-subtarefas.md](04-roadmap-subtarefas.md) — fases e checklist. Não executar sem aval.

## Regra de execução

Nenhuma fase começa sem aval explícito. Testes nunca rodam contra `backend/nexuslocal.db` vivo. Sem GitNexus. Deploy só pelo pipeline do `AGENTS.md`, e só quando pedido.
