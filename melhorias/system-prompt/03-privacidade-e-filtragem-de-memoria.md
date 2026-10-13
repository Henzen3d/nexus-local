# 🔒 Plano 03: Governança de Privacidade e Filtragem de Memória

Este documento aborda a proteção de dados pessoais e de conformidade no NexusLocal, estabelecendo filtros inteligentes para a injeção de memórias e perfil de usuário de acordo com a sensibilidade e o destino do modelo.

---

## 🚨 O Diagnóstico de Privacidade

O NexusLocal adota a filosofia *Local-First*, oferecendo máxima soberania de dados. No entanto, o sistema opera de forma híbrida e dinâmica:
- Modelos locais via Ollama/vLLM rodam na máquina do usuário sem tráfego externo.
- Modelos em nuvem (Groq, OpenRouter, Google Gemini, Cerebras, Sambanova) recebem as requisições via internet.

Atualmente, a função `build_memory_block` em [backend/memory.py](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py#L1387) injeta cegamente em **todas** as requisições:
1. **Identidade Completa:** Nome civil, pseudônimos, data de nascimento exata.
2. **Dados de Familiares:** Nome da esposa, profissão, dados do filho (idade, escola, hobbies).
3. **Resumos Globais:** Histórico de tópicos passados da família.

### O Risco em Tiers Gratuitos (Free Tiers)
Vários provedores de API gratuitos (ex: Gemini Free API, OpenRouter Free endpoints) preveem em seus Termos de Serviço que os dados trafegados podem ser retidos para telemetria ou treinamento de futuros modelos.  
Injetar a data de nascimento e o nome do filho do usuário em uma pergunta simples de desenvolvimento web (ex: *"Como centralizar uma div em CSS?"*) viola o princípio de minimização de dados do design ético de software.

---

## 🛡️ A Nova Estratégia de Filtragem em 3 Pilares

```
                            Requisição de Chat
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  Provedor Local       Provedor Remoto / Free
                 (Ollama, LMStudio)     (Groq, OpenRouter, Gemini)
                         │                     │
                         ▼                     ▼
                   Memória Total       Memória Sanitizada
                  (Todas as seções)     (Apenas Preferências +
                                         Identidade Essencial)
                                               │
                                 ┌─────────────┴─────────────┐
                                 ▼                           ▼
                           Pergunta Geral             Pergunta sobre Família
                         (Código, Teoria...)         ("Quantos anos meu filho tem?")
                                 │                           │
                                 ▼                           ▼
                         Família Omitida            Busca Vetorial On-Demand
                        (Minimização PII)            (Injeção just-in-time)
```

---

## 📋 Detalhamento dos Níveis de Informação

### Nível 1: Sempre Permitido (Informações Operacionais)
Mesmo em provedores públicos, são dados inofensivos e necessários para a boa experiência:
- Nome preferido / de tratamento (ex: "Osmar").
- Preferência de idioma (ex: "Português do Brasil").
- Estilo de resposta (ex: "respostas concisas", "código limpo", "evitar explicações prolixas").
- Tecnologias e stack padrão de preferência (ex: "FastAPI", "React", "Docker").

### Nível 2: PII Sensível (Restrito a Provedores Locais ou Consulta Específica)
- Nome completo civil e pseudônimos privados.
- Data de nascimento exata e idade.
- Detalhes de familiares (nomes de cônjuge, filhos, escolas, parentescos).
- Dados financeiros, contábeis ou de patrimônio.

---

## 🛠️ Especificação de Implementação

### 1. Classificação de Provedores por `privacy_tier`

Na tabela `providers` em [backend/database.py](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py), adicionar incrementalmente a coluna `is_local`:

```sql
ALTER TABLE providers ADD COLUMN is_local INTEGER DEFAULT 0;
```
- Provedores Ollama, LM Studio, TextGenWebUI → `is_local = 1`.
- Provedores remotos comerciais e gratuitos → `is_local = 0`.

### 2. Higienização na Injeção (`sanitize_memory_for_external`)

Em [backend/memory.py](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py):

```python
def sanitize_memory_for_external(
    facts: list[dict],
    profile: dict | None,
    user_message: str,
) -> tuple[list[dict], dict | None]:
    """Remove PII desnecessário para provedores externos a menos que a pergunta exija."""
    
    # Verifica se a mensagem atual cita expressamente termos de família/idade
    asks_family = bool(_RE_FAMILY_WORD.search(user_message or ""))
    asks_age = bool(_RE_USER_SELF_AGE.search(user_message or ""))
    
    sanitized_profile = dict(profile) if profile else {}
    if not asks_age and "full_name" in sanitized_profile:
        # Mantém apenas display_name para provedor externo
        sanitized_profile.pop("full_name", None)
        sanitized_profile.pop("birth_date", None)
    
    filtered_facts = []
    for f in facts:
        cat = f.get("category", "")
        # Se não perguntou de família, pula fatos da categoria family
        if cat == "family" and not asks_family:
            continue
        # Se for identidade, omite menções a pseudônimos e nascimento
        if cat == "identity" and not (asks_family or asks_age):
            text = f.get("fact", "")
            if "nascid" in text.lower() or "pseudônimo" in text.lower() or "casad" in text.lower():
                continue
        filtered_facts.append(f)
        
    return filtered_facts, sanitized_profile
```

### 3. Integração Transparente no `build_memory_context`

No arquivo [backend/orchestration/build_context.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/build_context.py#L38-L105):
- Antes de invocar `build_memory_block`, verificar se o provedor é remoto.
- Se for remoto, aplicar `sanitize_memory_for_external`.
- Se a pergunta for `"Qual a idade do meu filho?"`, o filtro detecta a palavra de parentesco e injeta pontualmente os fatos necessários para responder com precisão.

---

## 📈 Impacto e Segurança

1. **Vazamento Zero de Dados Familiares em Tarefas Gerais:** Durante desenvolvimento, geração de código, tradução e análise textual, nomes de cônjuges e dados de filhos não saem do servidor local.
2. **Conformidade Ética:** Alinhamento total aos princípios de Privacy by Design e GDPR/LGPD de minimização da coleta e trânsito de dados.
3. **Sem Perda de Inteligência:** Quando o usuário explicitamente conversa sobre sua família ou vida pessoal, o retrieval sob demanda reativa os fatos correspondentes.
