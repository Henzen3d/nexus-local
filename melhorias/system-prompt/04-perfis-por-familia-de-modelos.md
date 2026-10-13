# 🎭 Plano 04: Perfis de Comportamento por Família de Modelos (Prompt Profiles)

Este documento define a camada de especialização de prompt por família de arquitetura (`prompt_profile`). Diferentes famílias de modelos (Llama, Qwen, DeepSeek, Gemini, Mistral) reagem de forma distinta a um mesmo system prompt genérico; a camada de perfil absorve essas idiossincrasias sem poluir o prompt base global.

---

## 🎯 Por que Modelos Diferentes Precisam de Perfis Específicos?

O NexusLocal suporta failover dinâmico entre dezenas de modelos e provedores. No entanto:
1. **Modelos de Raciocínio (DeepSeek R1, Qwen QwQ, Gemini Flash Thinking):** Podem vazar ou parafrasear o raciocínio interno na resposta final, gastando tokens do usuário com meta-comentários como *"Primeiro pensei em X, depois mudei para Y"*.
2. **Modelos Ultracompactos (Llama 3.2 1B/3B, Qwen 2.5 3B):** Tendem a perder o foco em prompts longos e reintroduzir saudações robóticas redundantes (*"Claro! Aqui está o código que você pediu:"*).
3. **Modelos Especialistas em Código (Qwen Coder, DeepSeek Coder):** Têm forte tendência treinada a incluir scripts de instalação (`npm install`, `pip install`) mesmo quando o prompt pede código puro.

Em vez de sobrecarregar o `BASE_SYSTEM_PROMPT` com dezenas de exceções específicas, o harness injeta de **2 a 3 linhas cirúrgicas** baseadas na família identificada do modelo.

---

## 🏛️ Catálogo de Perfis por Família

```python
MODEL_FAMILY_PROFILES = {
    # Família 1: Modelos com Raciocínio Nativo (Reasoning / Thinking)
    "reasoning": (
        "DIRETRIZ DE RACIOCÍNIO:\n"
        "- Conduza seu raciocínio estritamente no canal interno apropriado.\n"
        "- NÃO resuma, repita ou justifique seu processo de pensamento na resposta final.\n"
        "- Entregue a resposta final diretamente com o resultado conclusivo."
    ),

    # Família 2: Modelos Compactos (<= 8B)
    "compact": (
        "DIRETRIZ DE CONCISÃO:\n"
        "- Seja direto e objetivo. Não inclua saudações, preâmbulos conversacionais nem frases de despedida.\n"
        "- Entregue o código solicitado imediatamente no primeiro caractere da resposta."
    ),

    # Família 3: Modelos Especialistas em Programação (Coder)
    "coder": (
        "DIRETRIZ DE CÓDIGO:\n"
        "- Escreva código modular, tipado e pronto para produção.\n"
        "- Omita instruções de terminal ou dependências a menos que expressamente solicitado."
    ),

    # Família 4: Família Google Gemini
    "gemini": (
        "DIRETRIZ DE FORMATAÇÃO:\n"
        "- Mantenha formatação Markdown rigorosa, evitando quebras arbitrárias dentro de blocos de código."
    ),

    # Padrão: Vazio (sem overhead de tokens para Claude, GPT-4o, etc.)
    "general": ""
}
```

---

## 🔍 Detecção Automática da Família do Modelo

A detecção é realizada em tempo de execução inspecionando o `model_id` e metadados cadastrados no banco de dados:

```python
def detect_model_family(model_id: str, reasoning_control: str | None = None) -> str:
    """Classifica o modelo em uma família comportamental para seleção do perfil."""
    m = model_id.lower()
    
    # Se o modelo tem controle de reasoning ativo ou é explicitamente de raciocínio
    if reasoning_control in ("thinking_budget", "reasoning_effort") or any(
        k in m for k in ("r1", "qwq", "thinking", "reasoner")
    ):
        return "reasoning"
        
    # Modelos coder especializados
    if any(k in m for k in ("coder", "code-llama", "codestral")):
        return "coder"
        
    # Modelos compactos / leves
    if any(k in m for k in ("1b", "2b", "3b", "7b", "8b", "mini", "flash-lite")):
        return "compact"
        
    # Família Gemini
    if "gemini" in m:
        return "gemini"
        
    return "general"
```

---

## 🧩 Integração no Fluxo de Montagem

No `build_composed_system_prompt` (definido no [Plano 02](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/02-composicao-projetos-e-fontes-rag.md)):

```python
family = detect_model_family(model_id, reasoning_control=m_row_reasoning)
profile_text = MODEL_FAMILY_PROFILES.get(family, "")

system_instruction = build_composed_system_prompt(
    base_prompt=BASE_SYSTEM_PROMPT,
    family_profile=profile_text,
    project_instructions=project_instructions,
    user_memory=sanitized_user_memory,
    runtime_flags=flags,
)
```

### Por que isso Preserva o Prefix Caching?
Porque para um mesmo modelo selecionado (ex: `gemini-1.5-flash`), os dois primeiros blocos do prompt:
`BASE_SYSTEM_PROMPT` + `MODEL_FAMILY_PROFILES["gemini"]`  
são **completamente idênticos e determinísticos** em todas as requisições enviadas para aquele modelo, garantindo o mais alto índice de cache hit possível no backend do provedor.

---

## 🎯 Resultados Esperados

1. **Eliminação de Resíduos de Raciocínio:** Modelos como DeepSeek R1 e QwQ respondem de forma limpa sem poluir a interface do usuário com cópias de raciocínio.
2. **Respostas Instantâneas em Modelos Leves:** Modelos 3B/7B eliminam preâmbulos inúteis como *"Sure, I'd be happy to help with that!"*.
3. **Custo Mínimo de Tokens:** O overhead de cada perfil é de apenas **20 a 35 tokens**, representando menos de 0.5% da janela de contexto.
