# NexusLocal — auditoria por simulação de uso

**Data:** 14/10/2026 · **base:** `af42ceeb3c276506e819684d01487b010a545fd2` · **branch:** `arena/35998e1d-nexus-local`.

## Veredito executivo

O produto já tem boa parte da infraestrutura prometida, mas **a primeira experiência self-hosted ainda falha antes da primeira resposta**. Depois de preparar uma conta e um provedor de teste, chat, troca de modelo, anexos, navegação mobile e Fusion textual funcionaram. Os maiores riscos são respostas fora do contexto, falsa sensação de cancelamento/privacidade e degradação silenciosa do RAG.

**Não é correto descrever o RAG atual como mera concatenação crua:** há chunking, embeddings, busca híbrida, orçamento e fontes delimitadas. O problema demonstrado foi outro: documentos aparecem como “Indexado” sem um único embedding; perguntas normais ficam sem trechos, enquanto uma pergunta que menciona explicitamente “arquivos” ativa o fallback lexical.

Nenhum código de produto foi alterado, nenhum commit de código de produto foi criado e nenhum banco de produção foi usado. Escritas ocorreram exclusivamente em dados sintéticos isolados, scripts de teste e nesta entrega.

## Notas diagnósticas (0–10)

Escala: 0 = inviável; 5 = parcialmente utilizável com falhas importantes; 10 = consistente, validado e robusto. São avaliações de engenharia, **não uma média estatística nem benchmark de qualidade de modelos**.

| Área | Nota | Motivo principal | Confiança |
|---|---:|---|---|
| UX | **4** | Onboarding bloqueado, privacidade imprecisa, ausência de editar/regenerar, estados enganosos | Alta |
| UI | **6** | Hierarquia agradável e layouts 1440/390 funcionais; falhas de contraste, nomes acessíveis e foco | Alta no Chromium; limitada em fontes/Safari |
| Performance | **5** | Streaming coalescido e fan-out paralelo; bundle inicial grande, varreduras lineares e ausência de cancelamento efetivo | Média; sem LLM externo real |
| Robustez | **4** | WAL, autenticação e alguns guardas existem; input tipado incorretamente derruba socket, duplicação e limites frágeis | Alta |
| RAG | **5** | Pipeline real e orçamento seletivo; degradação silenciosa e citações de projeto não chegam como fontes estruturadas ao chat | Alta para transporte/recuperação; não avaliou qualidade generativa |
| Fusion | **4** | Tolera um proposer com erro; Judge perde system do projeto, imagens quebram e orçamento não é por participante | Alta para defeitos reproduzidos |
| Cache | **3** | Isolamento por usuário e bloqueio de follow-up existem; escopo semântico incompleto, TTL e renovação defeituosos | Alta para provas determinísticas |

## Os 10 maiores ganhos

1. **Tornar o primeiro uso executável:** corrigir comando/dependências do launcher e oferecer bootstrap seguro do primeiro administrador. `B01/U01`.
2. **Fazer Ollama funcionar sem chave:** não enviar `Authorization: Bearer ` vazio. Erro reproduzido antes de qualquer resposta. `B02`.
3. **Isolar cache por contexto efetivo:** projeto, revisão documental, system, anexos, ferramentas e parâmetros; não apenas memória/usuário. `B03`.
4. **Preservar as evidências no Judge:** manter instruções, memória e RAG ao inserir o papel de juiz. `B06`.
5. **Fazer “Parar” parar o trabalho:** cancelamento no backend, persistência parcial e identificação de turno. Hoje a resposta completa reaparece após recarregar. `B11/U06`.
6. **Expor e recuperar RAG degradado:** separar texto indexado de vetores prontos e usar fallback lexical em perguntas relevantes, sem depender da palavra “arquivos”. `B05`.
7. **Fechar limites de contexto e multimodalidade do Fusion:** validar mensagem gigante, orçamento por modelo e tratar `content` como string OU lista. `B07/B08`.
8. **Não registrar credenciais bearer:** o access log padrão capturou JWTs inteiros na URL do WebSocket. `B13`.
9. **Corrigir promessa de privacidade:** armazenamento local não significa que memórias nunca são enviadas ao provedor. `U07/B14`.
10. **Corrigir acessibilidade e feedback básico:** nomes acessíveis, foco em sidebar oculta, contraste, erro traduzido e término real de Fusion/busca. `U02–U04/U08`.

## O que efetivamente foi validado

- Backend FastAPI e frontend Vite reais, SQLite novo e separado em `.cache/simulacao/qa.db`.
- **37 screenshots** de Chromium, incluindo 1440×900 e 390×844, login, onboarding, erros, modelos, projetos, biblioteca, anexos, streaming, cancelamento, Fusion e tema escuro.
- Playwright real + axe-core; HTTP e WebSocket reais. Fluxos gerativos usaram **servidor OpenAI-compatível determinístico**, explicitamente rotulado como simulação, depois dos testes sem configuração.
- Documento sintético de **42.689 caracteres / 62 chunks**, mais dois documentos, PDF corrompido, arquivo não suportado, arquivo vazio e upload de 26 MiB.
- Mensagem de 100 mil caracteres; conversa com 160 mensagens anteriores; seis WebSockets concorrentes; JSON com formato inválido; dois envios idênticos; encerramento de aba; erro 401 e 429 de provedor sintético.
- `npm run build`: passou; `npm test`: **50/50**; backend: **406 passaram, 5 falharam, 3 erros de fixture, 1 ignorado**. Não atribuir todos os testes vermelhos a defeitos de produto: parte depende de embeddings externos ou setup incompleto.
- `PRAGMA integrity_check`: `ok` antes e depois; nenhum lock reproduzido com seis turnos concorrentes.

### Números observados, não SLA

Um turno normal sintético teve primeiro token em **158,6 ms** e término em **365 ms**; Fusion de três provedores sintéticos, **510,2 ms / 692,5 ms**. Seis turnos simultâneos: primeiro token **179,1–196,5 ms**. Estes números incluem a latência artificial do fake e não estimam latência, custo monetário ou qualidade de APIs comerciais.

O histórico de 160 mensagens foi reduzido para **16 mensagens antigas + pergunta atual + system**, começando em `MARCADOR_144`. A mensagem individual gigante, porém, foi enviada intacta: aproximadamente **25.004 tokens estimados para orçamento de 6.144**.

## Limitações e honestidade da avaliação

- O sandbox não acessa HuggingFace, provedores comerciais, buscadores nem Google Fonts. A falha de download do embedder é **ambiental**; a ausência de estado degradado e recuperação adequada é **do produto**.
- Não houve inferência real de LLM/visão, avaliação de qualidade do Judge, medição empírica de viés, recall de embeddings reais ou custo em reais/dólares. Vision Relay foi auditado por código/testes existentes, não por transcrição visual real.
- MiniLM não foi baixado. As provas de escopo do cache usam vetores sintéticos e hit de fingerprint; não alegam medir taxa de falso positivo semântico real.
- Fontes remotas e glifos CJK/emoji não carregaram integralmente no Chromium mínimo. Os quadrados nos screenshots não provam corrupção de Unicode: conteúdo foi preservado no DOM, na API e no SQLite.
- Capturas mobile são viewport de navegador, não teste físico de teclado virtual/iOS. Axe não substitui leitor de tela. Tema escuro teve inspeção visual, não repetição integral de axe.
- Emulação offline não derrubou imediatamente todo WebSocket existente; o screenshot de envio offline não é prova suficiente de reconexão correta. Falha de sessão/socket e cancelamento foram também auditados no código.

## Arquivos

- [01-ux-ui.md](01-ux-ui.md): personas, cobertura visual e achados de experiência.
- [02-backend.md](02-backend.md): arquitetura, evidências técnicas, falhas e sugestões.
- [03-roadmap.md](03-roadmap.md): prioridade por impacto/esforço e critérios de aceite.
- [04-testes.md](04-testes.md): reprodução, resultados e regressão recomendada.
- [evidencias/](evidencias/): screenshots, JSON de DOM/axe/API, logs sanitizados, schema e medidas.
- Scripts: `tests/simulacao/`.

## Perguntas de produto — decisões não assumidas

1. O modo self-hosted é pessoal com bootstrap próprio ou instalação exclusivamente administrada para famílias/equipes? Cadastro público fechado é intencional; qual deve ser o primeiro acesso?
2. “Parar” deve abortar cobrança/trabalho imediatamente ou apenas ocultar a saída? A recomendação é cancelar; a interface atual não explica a diferença.
3. Fusion deve permitir vários modelos do mesmo provedor? Hoje o SQLite impõe um por provedor, mas a API aceita uma lista que resulta em HTTP 500.
4. Memória deve ser opt-in? Quais categorias podem seguir para APIs externas, inclusive quando Fusion mistura provedores locais e remotos?
5. Cache de perguntas factuais dinâmicas, busca web e documentos mutáveis deve ser opt-in ou proibido por padrão?
6. Qual referência prevalece para ações primárias e alvos de toque? DESIGN.md tem regra coral/seleção azul, mas também exemplos de botões de 36/40 px; a meta solicitada foi ≥44 px.
7. Qual SLA e teto de custo para Fusion: esperar todos, quorum, resposta parcial ou deadline global? Quantas citações verificáveis são obrigatórias no RAG?