# Harness exploratório de QA — 2026-10-14

Somente teste/documentação, sem monkeypatch do servidor de produto. **Nunca apontar para banco real.** Relatórios e resultados: `melhorias/simulacao-2026-10-14/`.

## Dependências e ambiente

Python `.venv`, dependências de `backend/requirements.txt`, Playwright; npm ci em frontend. `DB_PATH=$PWD/.cache/simulacao/qa.db` e JWT aleatório no processo do backend. Adicione `/.cache/` ao `.git/info/exclude` local antes de criar fixtures: essa pasta contém sessões/senhas efêmeras, não deve ser commitada.

Para este sandbox: `npm install --prefix .cache/simulacao @sparticuz/chromium@153.0.0 axe-core`. Use `executablePath()` do pacote e `inflate()` de `build/lambdafs.js` para `bin/al2023.tar.br`. Os scripts apontam para `/tmp/chromium`; execute com `LD_LIBRARY_PATH=/tmp/al2023/lib`. Em outra máquina instale o browser Playwright e adapte o caminho. As capturas são reais, não imagens geradas.

## Ordem de exploração

1. Iniciar `uvicorn backend.main:app` da raiz com env isolado; iniciar Vite com `--config tests/simulacao/vite.config.mjs`.
2. `browser_scout.py` captura login sem usuários. `seed_qa.py` cria duas contas fictícias no qa.db, grava senha aleatória SOMENTE em `.cache/simulacao/credentials.json`.
3. `browser_flows.py` testa primeira mensagem sem chaves. Não executar configuração fake antes de registrar esse resultado.
4. Iniciar `.venv/bin/uvicorn tests.simulacao.fake_provider:app --host 0.0.0.0 --port 8010 --no-access-log`. `configure_qa.py --session` configura modelos fictícios Ollama + chave dummy local e salva sessão QA em `.cache`.
5. Para repetir especificamente o bug Ollama vazio, remover a chave dummy SOMENTE do usuário QA no qa.db, enviar e depois restaurar com configure_qa.py. Não usar nenhuma API key real.
6. `browser_daily.py`, `api_flows.py`, `api_power.py` (nessa ordem). api_power reaproveita projeto criado pelo anterior e acrescenta dois providers sintéticos. api_flows sobrescreve seu arquivo de resultados; power/final leem e acrescentam resultados. Não rodar em paralelo.
7. `logic_probes.py`: independente dos servidores; usa seu próprio TemporaryDirectory e embeddings artificiais. Prova comportamento atual, não qualidade semântica real.
8. `browser_panels.py`, `browser_edges.py`, `final_probes.py`: sessão de `.cache/simulacao/session.json`. `UI_ONLY=1` no último pula seed de histórico/carga. Repetir configure_qa.py depois de testes 429 pode restaurar quotas da fixture; não há equivalência com reset em produção.
9. Encerrar servidores, sanitizar JWT/assinaturas dos logs antes de versionar, nunca adicionar `.cache`, storage, DB, binários ou pacotes.

O fake **não é um modelo de IA**. Saídas constantes validam transporte, estado e payload; não aprovam grounding, visão, factualidade ou viés. Os sleeps/selectors dos scripts são exploratórios. A suite de regressão assertiva proposta está no relatório 04-testes.md; esses scripts não devem ser inscritos como CI universal sem fixtures/teardown adicionais.

Alguns logs preservam tentativas iniciais falhas do harness, claramente distinguidas das evidências finais no relatório. Erros de extração JSON de memória produzidos pelas respostas constantes do fake são limitação da fixture, não achado de qualidade de LLM.
