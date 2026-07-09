# Plano de Implementação — Anexos de Arquivos (PDF, DOCX, Imagens)
**NexusLocal** · Documento técnico de planejamento

---

## 1. Visão Geral

Permitir que o usuário anexe arquivos ao chat, divididos em duas categorias com tratamento distinto:

- **Documentos de texto** (PDF, DOCX, TXT, CSV, MD) → extraídos como texto e injetados no prompt. Funciona com **qualquer modelo**.
- **Imagens** (PNG, JPG, WEBP) → enviadas em formato multimodal (base64) quando o modelo selecionado suporta visão, **ou** transparentemente roteadas por um **Vision Relay** (seção 5) quando não suporta — o usuário nunca precisa escolher ou saber disso.

O sistema precisa: detectar o tipo de arquivo, processá-lo corretamente, decidir a rota de processamento de imagem (direta ou via relay), e persistir os anexos no histórico da conversa com transparência sobre qual caminho foi usado.

---

## 2. Banco de Dados

### Nova tabela: `attachments`

```sql
CREATE TABLE IF NOT EXISTS attachments (
    id              TEXT PRIMARY KEY,
    message_id      TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    file_type       TEXT NOT NULL,        -- 'document' | 'image'
    size_bytes      INTEGER NOT NULL,
    extracted_text  TEXT,                 -- NULL para imagens
    storage_path    TEXT,                 -- caminho no disco (documentos E imagens)
    thumbnail_path  TEXT,                 -- apenas imagens, versão reduzida para preview
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);
```

### Nova coluna na tabela `models`

```sql
ALTER TABLE models ADD COLUMN supports_vision INTEGER DEFAULT 0;
```

Popular manualmente (ou via Fase 2 do plano de Context Registry, que já faz fetch de metadados) quais modelos suportam visão:

```sql
UPDATE models SET supports_vision = 1 WHERE name IN (
    'gemini-2.0-flash',
    'gemini-1.5-flash',
    'qwen/qwen2-vl-72b-instruct:free',
    'meta-llama/llama-3.2-11b-vision-instruct:free'
    -- adicionar conforme disponibilidade dos providers
);
```

### Diretório de armazenamento

```
backend/
  storage/
    attachments/
      {conversation_id}/
        {attachment_id}_{filename}
        {attachment_id}_thumb.jpg   (apenas imagens)
```

> Arquivos ficam no disco, não no banco — SQLite não é feito para armazenar blobs grandes com eficiência. O banco guarda apenas o caminho.

---

## 3. Backend — Processamento de Arquivos

### 3.1 Novas dependências

```
pypdf>=4.0.0          # extração de texto de PDF
pdfplumber>=0.11.0    # fallback para PDFs com tabelas complexas
python-docx>=1.1.0    # extração de texto de DOCX
pandas>=2.0.0         # CSV/XLSX (provavelmente já usado em outro contexto)
Pillow>=10.0.0        # geração de thumbnail e validação de imagem
python-magic>=0.4.27  # detecção confiável de MIME type (não confia só na extensão)
```

### 3.2 Novo módulo: `backend/attachments/`

```
backend/attachments/
  __init__.py
  extractors.py      # lógica de extração por tipo de arquivo
  validators.py       # valida tamanho, tipo, compatibilidade com modelo
  storage.py           # salvar/ler arquivos do disco
```

#### `extractors.py` — Lógica de extração

```python
# Pseudocódigo estrutural

async def extract_text_from_pdf(filepath: str) -> str:
    """Tenta pypdf primeiro (rápido); se resultado vazio ou malformado,
    tenta pdfplumber (mais lento mas melhor com tabelas)."""
    text = pypdf_extract(filepath)
    if not text.strip():
        text = pdfplumber_extract(filepath)
    if not text.strip():
        raise ExtractionError("PDF sem texto extraível — provavelmente escaneado. OCR necessário.")
    return text

async def extract_text_from_docx(filepath: str) -> str:
    ...

async def extract_text_from_csv(filepath: str) -> str:
    """Converte para markdown table — formato que os modelos entendem bem."""
    ...

def detect_file_category(mime_type: str) -> str:
    """Retorna 'document' ou 'image' baseado no MIME type real (via python-magic),
    não na extensão do arquivo (previne spoofing)."""
    ...
```

#### `validators.py` — Regras de negócio

```python
MAX_FILE_SIZE_MB = 20
MAX_PDF_PAGES = 100
SUPPORTED_DOCUMENT_TYPES = {'.pdf', '.docx', '.txt', '.csv', '.md'}
SUPPORTED_IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.webp'}

async def validate_attachment(file, model_id: str, db) -> ValidationResult:
    """
    1. Verifica tamanho do arquivo
    2. Verifica extensão/mime type suportado
    3. Se for imagem e o modelo selecionado NÃO suportar visão,
       NÃO bloqueia — apenas marca para roteamento via Vision Relay (seção 5)
    4. Retorna erro claro apenas para falhas reais (tamanho, tipo não suportado, corrupção)
    """
    ...
```

### 3.3 Novo endpoint: `backend/routers/attachments.py`

```
POST /api/attachments/upload
```

**Payload:** `multipart/form-data` com o arquivo + `model_id` (para validação de compatibilidade)

**Fluxo:**
1. Recebe arquivo, salva temporariamente
2. Detecta MIME type real via `python-magic`
3. Se documento → extrai texto, salva no campo `extracted_text`
4. Se imagem → valida compatibilidade com `model_id`, gera thumbnail
5. Persiste registro na tabela `attachments` (ainda sem `message_id`, vinculado depois)
6. Retorna `{ attachment_id, filename, file_type, preview_url, extracted_text_preview }`

```python
@router.post("/upload")
async def upload_attachment(
    file: UploadFile,
    model_id: str = Form(...),
):
    validation = await validate_attachment(file, model_id, db)
    if not validation.ok:
        raise HTTPException(400, detail=validation.error_message)

    category = detect_file_category(validation.mime_type)

    if category == "document":
        text = await extract_text(file, validation.mime_type)
        attachment_id = await save_attachment(file, extracted_text=text, ...)
    else:  # image
        thumb_path = await generate_thumbnail(file)
        attachment_id = await save_attachment(file, thumbnail_path=thumb_path, ...)

    return {"attachment_id": attachment_id, "file_type": category, ...}
```

---

## 4. Backend — Integração com o Chat (WebSocket)

### Modificação em `backend/routers/chat.py`

O payload do WebSocket passa a aceitar uma lista de `attachment_ids`:

```json
{
  "conversation_id": "...",
  "message": "resuma esse documento",
  "model_id": "gemini/flash-2.0",
  "provider_id": "gemini",
  "attachment_ids": ["att_123", "att_456"]
}
```

### Lógica de injeção no prompt

```python
async def build_message_content(user_message: str, attachment_ids: list[str], db):
    attachments = await fetch_attachments(attachment_ids, db)

    documents = [a for a in attachments if a.file_type == "document"]
    images    = [a for a in attachments if a.file_type == "image"]

    # Documentos: injeta texto extraído como contexto adicional
    if documents:
        doc_context = "\n\n".join([
            f"--- Conteúdo de {d.filename} ---\n{d.extracted_text}"
            for d in documents
        ])
        final_text = f"{doc_context}\n\n---\n\nPergunta do usuário: {user_message}"
    else:
        final_text = user_message

    # Imagens: monta conteúdo multimodal (formato OpenAI-compat)
    if images:
        content = [{"type": "text", "text": final_text}]
        for img in images:
            base64_data = await read_as_base64(img.storage_path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{img.mime_type};base64,{base64_data}"}
            })
        return content  # lista multimodal
    else:
        return final_text  # string simples
```

> **Ponto crítico:** o formato multimodal (`image_url` com base64) é o padrão OpenAI-compatible que Groq, OpenRouter, Gemini (via endpoint compat) e a maioria dos providers aceitam. Mas é necessário validar caso a caso — alguns providers podem exigir uma URL pública em vez de base64 inline.

### Validação de compatibilidade em tempo real

Diferente de bloquear o envio, o sistema decide silenciosamente a rota de processamento — envio multimodal direto ou desvio via Vision Relay (seção 5):

```python
content, meta = await build_message_content(user_message, attachment_ids, db, model_id=model_id)

if meta.get("relay_used"):
    # Registrar no histórico que houve relay, para exibir o badge de transparência (seção 5.6)
    relay_info = {"relay_model": meta["relay_model"]}
else:
    relay_info = None
```

---

## 5. Vision Relay — Roteamento Invisível para Modelos Sem Visão

### 5.1 Conceito

Quando o usuário anexa uma imagem mas o modelo selecionado não suporta visão, o backend **automaticamente** envia a imagem para um modelo intérprete fixo (vision-capable), obtém uma descrição textual detalhada, e injeta essa descrição como contexto adicional no prompt do modelo original. O usuário nunca precisa trocar de modelo ou saber que esse desvio aconteceu — apenas recebe uma resposta coerente.

```
Usuário anexa foto.jpg + "o que tem nessa imagem?"
Modelo ativo: Llama 3.3 70B (Cerebras — sem visão)

        ↓ backend detecta incompatibilidade
        ↓
Vision Relay → Gemini 2.0 Flash (modelo intérprete fixo)
   prompt interno: "Descreva esta imagem em detalhes objetivos,
   incluindo texto visível, objetos, pessoas, cores e contexto."
        ↓
Descrição retornada em texto
        ↓
Injetada no prompt do Llama 3.3 70B:
  "[Descrição da imagem foto.jpg]: <descrição gerada>
   ---
   o que tem nessa imagem?"
        ↓
Llama 3.3 70B responde normalmente, usuário recebe a resposta
```

### 5.2 Trade-off — Importante Documentar

A resposta final **não analisa a imagem diretamente** — analisa uma descrição textual dela. Isso é adequado para:
- "O que tem nessa imagem?" / "Descreva essa cena"
- "Transcreva o texto dessa foto" (OCR via descrição)
- Identificação de objetos, pessoas, contexto geral

Mas degrada em:
- Análise visual de nuance fina ("essa mancha é mofo ou umidade?")
- Comparação detalhada entre múltiplas imagens
- Qualquer julgamento que dependa de detalhe que o intérprete não tenha descrito

É um efeito "telefone sem fio" — cada camada de tradução perde informação. Funciona bem para a maioria dos usos cotidianos, mas não é equivalente a visão nativa.

### 5.3 Configuração do Modelo Intérprete

Nova seção em **Configurações → Ferramentas**, ao lado do Enhancer e do Fusion:

```sql
CREATE TABLE IF NOT EXISTS vision_relay_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    relay_provider_id   TEXT NOT NULL,
    relay_model_id      TEXT NOT NULL,
    relay_system_prompt TEXT DEFAULT '...',
    enabled             INTEGER DEFAULT 1,
    cache_descriptions  INTEGER DEFAULT 1   -- reaproveitar descrição p/ mesma imagem
);
```

**System Prompt padrão do intérprete:**

```
Você é um sistema de descrição de imagens. Descreva a imagem em detalhes
objetivos e completos: objetos, pessoas, texto visível (transcreva
literalmente), cores, contexto da cena, e qualquer informação relevante.

Seja exaustivo mas direto. Não faça julgamentos de valor. Não adicione
introduções como "esta imagem mostra". Vá direto à descrição.
```

**Recomendação de modelo padrão:** `gemini-2.0-flash` — free tier generoso (1500 req/dia), boa qualidade de descrição, latência baixa.

### 5.4 Endpoint e Lógica

Novo arquivo: `backend/vision_relay/relay.py`

```python
async def get_or_generate_descriptions(images: list[Attachment], db) -> list[DescribedImage]:
    config = await get_vision_relay_config(db)
    results = []

    for img in images:
        # Cache: mesma imagem já descrita antes? (hash do arquivo)
        if config.cache_descriptions:
            cached = await get_cached_description(img.file_hash, db)
            if cached:
                results.append(cached)
                continue

        base64_data = await read_as_base64(img.storage_path)
        provider = await get_provider(config.relay_provider_id, db)

        description = await provider.describe_image(
            model=config.relay_model_id,
            image_base64=base64_data,
            mime_type=img.mime_type,
            system_prompt=config.relay_system_prompt,
        )

        await save_description_cache(img.file_hash, description, db)
        results.append(DescribedImage(filename=img.filename, description=description))

    return results
```

### 5.5 Cache de Descrições

Como gerar uma descrição custa uma chamada de API extra, vale cachear por **hash do conteúdo do arquivo** (não por `attachment_id`, já que a mesma imagem pode ser reenviada em conversas diferentes):

```sql
CREATE TABLE IF NOT EXISTS vision_descriptions_cache (
    file_hash    TEXT PRIMARY KEY,   -- SHA-256 do conteúdo do arquivo
    description  TEXT NOT NULL,
    relay_model  TEXT NOT NULL,
    created_at   TEXT DEFAULT (datetime('now'))
);
```

Isso se integra naturalmente ao sistema de cache já existente no NexusLocal (Fase de Caching Inteligente) — é o mesmo princípio de cache exato, aplicado a um novo tipo de conteúdo.

### 5.6 Transparência — Badge de Relay

Mesmo sendo automático, a resposta deve indicar que houve um desvio, reaproveitando o sistema de badges já planejado (Plano de Badge de Modelo):

```
┌──────────────────────────────────────────────┐
│ 🔷 Llama 3.3 70B   14:32                       │
│ 🔄 Imagem interpretada via Gemini 2.0 Flash    │  ← linha adicional discreta
│                                                │
│ Essa foto mostra um vazamento na tubulação... │
└──────────────────────────────────────────────┘
```

```css
.message-relay-notice {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-4);
  margin-bottom: 6px;
}
.message-relay-notice svg { color: var(--teal); }
```

Hover no aviso mostra: "A imagem foi descrita por Gemini 2.0 Flash porque Llama 3.3 70B não processa imagens nativamente. A resposta é baseada nessa descrição textual."

### 5.7 Falha do Relay

Se o modelo intérprete estiver indisponível (sem chave configurada, erro de API, rate limit):

```python
try:
    descriptions = await get_or_generate_descriptions(images, db)
except RelayError as e:
    await ws.send_json({
        "type": "error",
        "message": "Não foi possível processar a imagem anexada. "
                    "Verifique a configuração do Vision Relay em Configurações → Ferramentas."
    })
    return
```

Diferente de bloquear silenciosamente por incompatibilidade, aqui o erro só aparece se o **próprio relay falhar** — não pela ausência de suporte a visão no modelo principal, que é justamente o cenário que o relay existe para resolver.

### 5.8 Interação com o Modo Fusion

Quando o Fusion estiver ativo e houver imagem anexada: cada modelo paralelo que não suportar visão recebe automaticamente a descrição via relay (gerada **uma única vez** e reaproveitada para todos os modelos do preset, evitando N chamadas redundantes ao intérprete).

---

## 6. Frontend — Upload e Preview

### 5.1 Novo componente: `frontend/src/components/AttachmentButton.tsx`

Botão de "+" (Plus, do Lucide React) dentro do input, ao lado do model selector pill — mesmo padrão usado por Claude.ai, ChatGPT e Gemini para anexos e ações extras.

```typescript
interface AttachmentButtonProps {
  onUpload: (attachment: Attachment) => void
  currentModelId: string
  currentModelSupportsVision: boolean
}
```

**Fluxo do componente:**
1. Clique abre seletor de arquivo nativo (`<input type="file" multiple accept="...">`)
2. Ao selecionar, dispara upload imediato para `/api/attachments/upload`
3. Mostra spinner de progresso durante o upload
4. Ao concluir, renderiza um **chip de anexo** acima do input (thumbnail para imagem, ícone de arquivo + nome para documento)

### 5.2 Novo componente: `frontend/src/components/AttachmentChip.tsx`

Chip visual que aparece **acima do textarea**, antes do envio:

```
┌────────────────────────────────────────────┐
│ [📄 relatorio.pdf]  [🖼️ foto.jpg]  [x] [x] │  ← chips removíveis
├────────────────────────────────────────────┤
│  textarea de mensagem...                   │
├────────────────────────────────────────────┤
│  [+] [Groq · Llama ▾]         [✦][🎙][▷] │
└────────────────────────────────────────────┘
```

```css
.attachment-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-pill);
  font-size: 12.5px;
}
.attachment-chip-thumb {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  object-fit: cover;
}
.attachment-chip-remove {
  color: var(--text-4);
  cursor: pointer;
}
.attachment-chip-remove:hover { color: var(--error); }
```

### 5.3 Validação client-side (antes do upload)

```typescript
const MAX_SIZE_MB = 20
const ALLOWED_TYPES = {
  document: ['.pdf', '.docx', '.txt', '.csv', '.md'],
  image: ['.png', '.jpg', '.jpeg', '.webp']
}

function validateFile(file: File, currentModel: Model): ValidationResult {
  if (file.size > MAX_SIZE_MB * 1024 * 1024) {
    return { ok: false, error: `Arquivo muito grande (máx. ${MAX_SIZE_MB}MB)` }
  }

  const ext = getExtension(file.name)
  const isImage = ALLOWED_TYPES.image.includes(ext)

  if (isImage && !currentModel.supports_vision) {
    return {
      ok: false,
      error: `${currentModel.display_name} não processa imagens. Troque de modelo primeiro.`
    }
  }

  return { ok: true }
}
```

### 5.4 Indicador visual no Model Selector

Quando o usuário já anexou uma imagem e tenta trocar para um modelo sem visão, o dropdown deve **desabilitar visualmente** (não impedir, mas avisar) os modelos incompatíveis:

```tsx
<button
  className={`model-option ${!m.supports_vision && hasImageAttached ? 'incompatible' : ''}`}
  disabled={!m.supports_vision && hasImageAttached}
>
  {m.display_name}
  {!m.supports_vision && hasImageAttached && (
    <span className="incompatible-hint">Sem suporte a imagem</span>
  )}
</button>
```

---

## 7. Frontend — Exibição no Histórico

Mensagens do usuário que tiveram anexos devem mostrar isso no histórico:

```tsx
{message.attachments?.length > 0 && (
  <div className="message-attachments">
    {message.attachments.map(att => (
      <AttachmentChip key={att.id} attachment={att} readonly />
    ))}
  </div>
)}
```

Para documentos, um clique no chip pode expandir e mostrar o texto extraído (útil para debug/revisão). Para imagens, um clique abre um preview em modal/lightbox.

---

## 8. Tratamento de Erros e Casos-Limite

| Cenário | Comportamento |
|---|---|
| PDF escaneado (sem texto extraível) | Erro claro: "Este PDF parece ser escaneado. Extração de texto não disponível — considere anexar como imagem em vez de PDF." |
| Arquivo corrompido | Erro genérico de upload, log detalhado no backend |
| Múltiplos arquivos grandes somando > limite de contexto do modelo | Aviso antes do envio: "O conteúdo extraído pode exceder o contexto do modelo selecionado (~45K tokens estimados de 32K disponíveis)" — reutiliza a lógica do `ContextBar` já implementado |
| Imagem em modelo sem visão | **Não bloqueia** — roteada automaticamente via Vision Relay (seção 5), com badge de transparência na resposta |
| Vision Relay indisponível (sem chave, erro de API, rate limit) | Erro claro apontando para a configuração: "Não foi possível processar a imagem. Verifique o Vision Relay em Configurações → Ferramentas." |
| Upload interrompido (conexão cai) | Cleanup de arquivos temporários órfãos via job periódico ou verificação no startup |

---

## 9. Integração com Funcionalidades Existentes

### Cache (exato/semântico)
O hash do cache exato já inclui todas as mensagens da conversa — precisa ser estendido para incluir também o `extracted_text` dos anexos, senão duas perguntas idênticas com anexos diferentes gerariam falso cache hit.

```python
# Ajuste em cache/manager.py — _hash_messages()
def _hash_messages(self, model_id: str, messages: list, attachments_text: str = "") -> str:
    key = model_id + json.dumps(messages, ...) + attachments_text
    return hashlib.sha256(key.encode()).hexdigest()
```

### Context Bar
A estimativa de tokens precisa somar o texto extraído dos anexos, não só o conteúdo digitado:

```typescript
// Ajuste em utils/tokens.ts
export function estimateTokens(messages: Message[], attachmentsText: string = ''): number {
  const chars = messages.reduce((sum, m) => sum + m.content.length, 0) + attachmentsText.length
  ...
}
```

### Fusion (quando implementado)
Anexos devem ser replicados para **todos os modelos paralelos** — se um dos modelos do preset Fusion não suportar visão, esse modelo específico é pulado silenciosamente (ou retorna erro tratado) enquanto os outros processam normalmente.

---

## 10. Arquivos a Criar / Modificar

| Arquivo | Ação |
|---|---|
| `backend/attachments/__init__.py` | **Criar** |
| `backend/attachments/extractors.py` | **Criar** — lógica de extração por tipo |
| `backend/attachments/validators.py` | **Criar** — validação de tamanho/tipo (sem checagem de bloqueio por visão) |
| `backend/attachments/storage.py` | **Criar** — persistência em disco |
| `backend/routers/attachments.py` | **Criar** — endpoint de upload |
| `backend/vision_relay/__init__.py` | **Criar** |
| `backend/vision_relay/relay.py` | **Criar** — lógica de descrição via modelo intérprete |
| `backend/routers/vision_relay.py` | **Criar** — endpoints de configuração do relay |
| `backend/routers/chat.py` | **Modificar** — aceitar `attachment_ids`, decidir rota multimodal direta vs. relay |
| `backend/database.py` | **Modificar** — tabelas `attachments`, `vision_relay_config`, `vision_descriptions_cache`; coluna `supports_vision` em `models` |
| `backend/cache/manager.py` | **Modificar** — incluir texto de anexos e descrições no hash |
| `backend/main.py` | **Modificar** — registrar routers de attachments e vision_relay |
| `requirements.txt` | **Modificar** — adicionar pypdf, pdfplumber, python-docx, Pillow, python-magic |
| `frontend/src/components/AttachmentButton.tsx` | **Criar** |
| `frontend/src/components/AttachmentChip.tsx` | **Criar** |
| `frontend/src/components/VisionRelaySettings.tsx` | **Criar** — configuração do modelo intérprete em Configurações → Ferramentas |
| `frontend/src/components/MessageInput.tsx` | **Modificar** — integrar botão e chips |
| `frontend/src/components/MessageBubble.tsx` | **Modificar** — exibir anexos e badge de relay no histórico |
| `frontend/src/utils/tokens.ts` | **Modificar** — incluir texto de anexos/descrições na estimativa |
| `frontend/src/types.ts` | **Modificar** — adicionar interfaces `Attachment` e `RelayInfo` |
| `frontend/src/api/client.ts` | **Modificar** — método de upload e configuração do relay |

---

## 11. Sequência de Implementação Recomendada

```
1. Banco de dados
   → Tabela attachments + coluna supports_vision em models
   → Tabelas vision_relay_config e vision_descriptions_cache
   → Popular supports_vision manualmente para os modelos conhecidos

2. Backend — Extração de documentos (PDF/DOCX/CSV/TXT)
   → extractors.py + endpoint de upload
   → Testar com arquivos reais de cada tipo

3. Backend — Suporte a imagens (envio direto)
   → validators.py (detecção de tipo, sem bloqueio)
   → Geração de thumbnail
   → Formato multimodal na chamada ao provider (quando modelo suporta)

4. Backend — Vision Relay
   → relay.py com lógica de descrição via modelo intérprete fixo
   → Cache de descrições por hash de arquivo
   → Endpoint de configuração (VisionRelaySettings)

5. Backend — Integração com chat.py
   → Aceitar attachment_ids no payload WS
   → Decidir rota: multimodal direto vs. relay, conforme supports_vision
   → Anexar relay_info à mensagem persistida quando houver desvio

6. Frontend — Upload básico
   → AttachmentButton + chips
   → Validação client-side (tamanho, tipo — sem bloqueio por visão)

7. Frontend — Exibição no histórico
   → Anexos em mensagens antigas
   → Preview de imagem em modal
   → Badge de transparência do Vision Relay quando aplicável

8. Integrações finas
   → Cache: incluir anexos e descrições no hash
   → ContextBar: incluir tokens de anexos e descrições
   → Fusion: relay compartilhado entre modelos paralelos incompatíveis

9. Testes de borda
   → PDF escaneado, arquivo corrompido, múltiplos anexos grandes
   → Relay indisponível (sem chave, erro de API, rate limit)
```

---

## 12. Resumo Executivo

| Aspecto | Detalhe |
|---|---|
| **Complexidade** | Alta |
| **Tempo estimado** | 16–22h (documentos + imagem direta + vision relay) |
| **Dependências novas** | `pypdf`, `pdfplumber`, `python-docx`, `Pillow`, `python-magic` |
| **Risco principal** | Formato multimodal varia entre providers no envio direto; disponibilidade do modelo intérprete no relay |
| **Mitigação** | Começar suporte de imagem direta só com Gemini; Vision Relay com fallback claro se o intérprete falhar |
| **Pré-requisito recomendado** | Ter a Fase 2 do Context Registry pronta (fetch automático), pois o mesmo endpoint frequentemente retorna se o modelo suporta visão — evita popular `supports_vision` manualmente |

---

## 13. Nota Estratégica

Sugiro dividir esta implementação em **três entregas**:

**Entrega 1 — Documentos apenas** (PDF, DOCX, TXT, CSV)
- Não depende de modelo com visão — funciona com **tudo que você já tem configurado**
- Complexidade menor, valor imediato alto (resumir PDFs, analisar planilhas, etc.)
- ~6h de trabalho

**Entrega 2 — Imagens com envio direto** (PNG, JPG, WEBP)
- Apenas para modelos que já suportam visão nativamente (Gemini, alguns do OpenRouter)
- Formato multimodal pode ter particularidades por provider — mais tempo de testes
- ~5-6h de trabalho, idealmente após confirmar bom funcionamento da Entrega 1

**Entrega 3 — Vision Relay** (roteamento invisível)
- Elimina a necessidade do usuário pensar em compatibilidade de modelo
- Depende da Entrega 2 estar estável (o relay usa o mesmo caminho multimodal, só que com um modelo fixo escolhido pelo sistema)
- Inclui o badge de transparência e o cache de descrições
- ~5-6h de trabalho — pode ser adiada sem prejuízo funcional (usuário simplesmente escolhe manualmente um modelo com visão até esta entrega existir)
