# 🧠 System Prompt & Harness Architecture — Multi+ (NexusLocal)

Este diretório centraliza o diagnóstico, a especificação técnica e os planos de execução para a modernização do **System Prompt** e do **Harness de Orquestração** do Multi+ / NexusLocal.

---

## 🎯 O que é o "Harness" do NexusLocal?

Em sistemas modernos de IA, o termo **Harness** (arreio/armadura/estrutura de controle) designa toda a infraestrutura de engenharia construída *em torno* dos modelos de linguagem. O LLM em si é apenas o motor de inferência estocástico; o harness é o responsável por:
1. **Montagem do Contexto (Prompt Assembly):** Orquestrar o System Prompt base, perfis por família de modelos, memórias do usuário, instruções de projetos e flags dinâmicas de runtime.
2. **Isolamento de Segurança (Prompt Injection Defense):** Garantir que dados recuperados (RAG, buscas web, arquivos) sejam tratados estritamente como *dados*, e nunca como instruções operacionais.
3. **Privacidade e Governança:** Blindar dados pessoais do usuário contra vazamento acidental para provedores terceiros ou tiers gratuitos sujeitos a treinamento.
4. **Resiliência e Failover:** Detectar timeouts de primeiro token (TTFT), ler headers de quota proativamente e chavear provedores transparentemente em cascata.
5. **Ciclo de Vida de Artefatos:** Extrair código e documentos estruturados para renderização rica, download e versionamento automático no frontend.
6. **Desempenho e Caching:** Estruturar prompts para aproveitar o *Prefix Caching* dos provedores (Gemini, Anthropic, OpenAI) e otimizar latência percebida com streaming coalescido.

---

## 🔍 Diagnóstico do Estado Atual

A análise profunda do código atual (`backend/orchestration/build_context.py`, `backend/projects/context_builder.py`, `backend/memory.py`, `backend/orchestration/artifacts.py` e `backend/routers/chat.py`) revelou 6 pontos críticos que motivam esta reestruturação:

| Ponto Crítico | Onde Ocorre | Impacto no NexusLocal |
| :--- | :--- | :--- |
| **1. Substituição de Projetos** | `build_context.py` / `context_builder.py` | Quando um `project_id` está ativo, o contexto do projeto substitui as regras do sistema base em vez de compor. Regras como "sem emojis", "sem tool calls simuladas" e formatação de artefatos podem ser perdidas. Além disso, existe duplicação de `BASE_SYSTEM` em dois arquivos com divergências em potencial. |
| **2. Exposição de Privacidade em Free Tiers** | `memory.py` (`build_memory_block`) | Nome completo, ano de nascimento, pseudônimo e detalhes de familiares (esposa, filho, escola) são injetados por padrão no system prompt, sendo transmitidos a provedores de nuvem gratuitos (Groq, OpenRouter, Gemini Free) que podem reter dados para treino. |
| **3. Prompt Base Negativo vs Positivo** | `BASE_SYSTEM_PROMPT` | O prompt atual é dominado por proibições ("NÃO dê instruções de empacotamento", "NÃO use emojis", "Você não deve gerar chamadas fictícias"). Modelos compactos (3B a 8B) respondem com muito mais aderência a instruções afirmativas e concisas. |
| **4. Risco de Prompt Injection em RAG** | Chunks de arquivos, web search e chats | Textos recuperados da web ou de arquivos enviados entram sem tags delimitadoras estritas (`<fonte>...</fonte>`), permitindo que um arquivo ou site malicioso injete instruções de fuga ("Ignore previous instructions"). |
| **5. Prefix Caching Subótimo** | Montagem sequencial do contexto | Componentes variáveis (memória dinâmica, flags de áudio/web/imagem) são injetados antes ou misturados, invalidando o prefix cache de provedores como Gemini, que esperam prefixos estáticos idênticos no início. |
| **6. Detecção Frágil de Títulos de Artefatos** | `artifacts.py` | Para blocos de código (`py`, `ts`, `json`), o título padrão é genérico (`PYTHON Code`). Se o modelo colocar `# script.py` na primeira linha, o parser não aproveita esse nome de arquivo para o título do artefato. |

---

## 🗺️ Índice dos Planos de Melhoria

A iniciativa foi dividida em planos modulares e incrementais:

- [**01-novo-system-prompt-base.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/01-novo-system-prompt-base.md)  
  *Especificação do novo `BASE_SYSTEM_PROMPT` afirmativo, neutro em identidade, econômico em tokens (~280 tokens), com regras claras de artefatos, idioma e honestidade.*

- [**02-composicao-projetos-e-fontes-rag.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/02-composicao-projetos-e-fontes-rag.md)  
  *Arquitetura de composição em camadas (Base + Projeto + Fontes), unificação de constantes em `build_context.py` e encapsulamento de RAG com `<fonte id="..." origem="...">` anti-injection.*

- [**03-privacidade-e-filtragem-de-memoria.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/03-privacidade-e-filtragem-de-memoria.md)  
  *Estratégia de higienização de memória para provedores externos: injeção seletiva (apenas preferências e identidade essencial), isolando dados de familiares e datas sensíveis para retrieval sob demanda.*

- [**04-perfis-por-familia-de-modelos.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/04-perfis-por-familia-de-modelos.md)  
  *Camada de `prompt_profile` dinâmica por arquitetura: modelos de reasoning (não vazar pensamentos na resposta final), modelos pequenos (aderência reforçada) e modelos de código.*

- [**05-harness-resiliencia-latencia-e-cache.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/05-harness-resiliencia-latencia-e-cache.md)  
  *Aprimoramentos de harness: timeout proativo de primeiro token (TTFT de 8s), parser tolerante de filenames em `artifacts.py`, leitura de headers de rate limit e coalescência de WebSocket.*

- [**06-suite-de-testes-e-regressao.md**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/06-suite-de-testes-e-regressao.md)  
  *Bateria de 15 testes de regressão automatizados para rodar em isolamento (SQLite temporário descartável) para homologar o harness entre famílias de modelos (Llama, Gemini, Qwen, DeepSeek).*

---

## 🛡️ Regras de Ouro de Execução

1. **Integridade de Produção:** Qualquer alteração no backend deve respeitar as regras do [AGENTS.md](file:///j:/Arquivos%20Osmar/Multi+/AGENTS.md) — isolamento total de testes em banco temporário descartável, sem rodar testes no `nexuslocal.db` ao vivo.
2. **Retrocompatibilidade de Banco:** Caso novas colunas sejam necessárias (ex: `privacy_tier` em provedores), utilizar bloco `try/except sqlite3.OperationalError` em `backend/database.py`.
3. **Orçamento de Tokens:** O system prompt base consolidado não deve exceder 350 tokens, preservando a janela de contexto de modelos compactos de 8k e respeitando os limites estritos de TPM de provedores gratuitos (ex: Groq).
