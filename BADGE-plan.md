# Plano: Badge de Modelo por Mensagem (NexusLocal)

## Objetivo

Em conversas onde o usuário pode trocar de modelo (Anthropic, OpenAI, Google, etc.), cada mensagem deve exibir de forma sempre visível:
- Horário do prompt
- Modelo usado (badge)

E, ao passar o mouse sobre o badge do modelo, mostrar o provedor e o id técnico do modelo. A data completa continua aparecendo só no hover do horário, como já funciona hoje.

**Stack:** React + TypeScript + Vite (frontend) · Python + FastAPI + SQLite (backend)

---

## 1. Backend (FastAPI + SQLite)

### 1.1 Schema

Adicionar colunas na tabela `messages`:

```sql
ALTER TABLE messages ADD COLUMN model_id TEXT;
ALTER TABLE messages ADD COLUMN provider TEXT;
```

Não é necessário duplicar o "nome bonito" do modelo no banco. Mantenha um catálogo fixo no código — mais fácil de atualizar quando surgirem novos modelos:

```python
# models_catalog.py
MODEL_CATALOG = {
    "claude-sonnet-5": {"display_name": "Sonnet 5", "provider": "Anthropic"},
    "claude-opus-4-8": {"display_name": "Opus 4.8", "provider": "Anthropic"},
    "gpt-4o": {"display_name": "GPT-4o", "provider": "OpenAI"},
    "gemini-2.5-pro": {"display_name": "Gemini 2.5 Pro", "provider": "Google"},
    # ...
}

def get_model_meta(model_id: str) -> dict:
    return MODEL_CATALOG.get(model_id, {"display_name": model_id, "provider": "Desconhecido"})
```

### 1.2 Migração de dados existentes

Como o projeto usa SQLite, um script simples de migração resolve (ou Alembic, se já estiver configurado). Para mensagens antigas sem `model_id`, definir um valor padrão como `"legacy-unknown"`, para não quebrar a UI.

### 1.3 Modelo de resposta (Pydantic)

```python
class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime
    model_id: str | None
    provider: str | None
    model_display_name: str | None  # calculado via get_model_meta ao montar a resposta
```

### 1.4 Gravação no momento certo

No endpoint que cria a mensagem/resposta do assistente, salvar o `model_id` **efetivamente usado na chamada** — pegue direto do parâmetro da requisição que gerou a resposta, não do "modelo selecionado agora na tela". Isso evita inconsistência se o usuário trocar de modelo rapidamente entre o envio e a resposta.

**Se a resposta é streamada:** grave o `model_id` no início do registro, antes do streaming começar — não depois que a stream terminar.

---

## 2. Frontend (React + TypeScript)

### 2.1 Tipo

```typescript
interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  createdAt: string;
  modelId?: string;
  provider?: string;
  modelDisplayName?: string;
}
```

### 2.2 Componente `ModelBadge`

```tsx
function ModelBadge({ modelId, provider, displayName }: {
  modelId?: string;
  provider?: string;
  displayName?: string;
}) {
  if (!displayName) return null;
  return (
    <span
      className="model-badge"
      title={`Provedor: ${provider ?? "Desconhecido"}\nModelo: ${modelId}`}
    >
      {displayName}
    </span>
  );
}
```

### 2.3 Uso junto ao timestamp

```tsx
<div className="message-meta">
  <span className="timestamp" title={fullDate}>{time}</span>
  <span className="separator">·</span>
  <ModelBadge
    modelId={message.modelId}
    provider={message.provider}
    displayName={message.modelDisplayName}
  />
</div>
```

### 2.4 CSS (sugestão)

- Pill pequeno, `font-size: 11px`
- Cor neutra ou na paleta cream/coral do NexusLocal
- O atributo `title` nativo do HTML já cobre o tooltip — não é necessário adicionar biblioteca extra só para isso

---

## 3. Pontos de atenção específicos do projeto

| Ponto | Cuidado |
|---|---|
| **Regeneração de resposta / branching** | Se o app guarda múltiplas versões de uma resposta, cada versão precisa ter seu próprio `model_id` — confirmar se a tabela atual suporta isso ou se sobrescreve o registro. |
| **SQLite + concorrência** | Como é single-file, atenção a writes simultâneos se houver múltiplas abas/streams gravando ao mesmo tempo. |
| **Streaming** | Gravar `model_id` no início do registro, antes da stream começar. |
| **Mensagens legadas** | Definir fallback visual (ex: "Modelo desconhecido") para registros sem `model_id`. |

---

## 4. Próximos passos sugeridos

1. Rodar a migração no SQLite (adicionar colunas)
2. Atualizar o endpoint de criação de mensagem para persistir `model_id`
3. Atualizar o serializer/schema de saída para incluir `provider` e `model_display_name`
4. Criar o componente `ModelBadge` no frontend
5. Integrar o badge ao lado do timestamp existente
6. Testar com troca de modelo no meio da conversa e com regeneração de resposta