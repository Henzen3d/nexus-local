# 📐 02 - Arquitetura do Chat Input & Transição Dinâmica
**Multi+ (NexusLocal) — Engenharia de Componentes, JSX e Contratos**

Este documento estabelece a arquitetura técnica, modelo de estados e fluxos de renderização para a transformação do campo de mensagem em um input inteligente de **Linha Única**, com transição dinâmica de ações e migração do seletor para o rodapé.

---

## 🏗️ Anatomia dos Dois Modos de Exibição

O componente `MessageInput` operará em dois modos de layout claramente distintos através da propriedade `isEmpty`:

```mermaid
graph TD
    A[ChatWindow] -->|isEmpty = messages.length === 0| B(Modo Inicial / Empty State)
    A -->|!isEmpty = conversa ativa| C(Modo Ativo / Single Line Streamlined)
    
    B --> B1[Card Amplo Multilinha: ~110px]
    B --> B2[Textarea com foco no acolhimento]
    B --> B3[Barra de ações interna com + e Envio/Voz]
    
    C --> C1[Barra Compacta de Linha Única: ~44px]
    C --> C2[Linha interna inline unificada: + | textarea | ações]
    C --> C3[Chips de anexos empilhados no topo]
    C --> C4[Rodapé externo: Disclaimer à esq + Model Selector à dir]
```

---

## 1. Modo Conversa Ativa: Barra Compacta de Linha Única

### 1.1 Árvore Estrutural do JSX Corrigida (Evitando Conflito de Flex)

Para evitar o erro de layout onde `display: flex` no card colocaria os chips de anexo lado a lado com o textarea, o componente adota uma estrutura em camadas verticais:

```tsx
<div className="input-wrapper" style={wrapperStyle}>
  <div className={`input-card ${isCompact ? 'compact-mode' : ''} ${enhanceFlash ? 'enhance-flash' : ''}`}>
    
    {/* CAMADA 1: Preview de Anexos (sempre empilhado no topo do card) */}
    {attachments.length > 0 && (
      <div className="input-attachments-preview">
        {attachments.map((att) => (
          <AttachmentChip key={att.id} attachment={att} onRemove={...} />
        ))}
      </div>
    )}

    {/* CAMADA 2: Linha Inline Unificada do Composer */}
    <div className="composer-single-line-row">
      <PlusActionMenu ... />
      
      <textarea
        ref={textareaRef}
        className="composer-textarea-inline"
        value={text}
        rows={1}
        placeholder={placeholderText}
        onChange={...}
        onKeyDown={handleKeyDown}
      />

      <div className="composer-actions-right">
        {renderRightActions()}
      </div>
    </div>
  </div>

  {/* CAMADA 3: Rodapé Externo (Disclaimer à esquerda, Modelo à direita) */}
  <div className="input-footer-row">
    <span className="input-footer-disclaimer">
      {t('chat.inputHint', {
        defaultValue: 'O NexusLocal é uma IA e pode cometer erros. Por favor, verifique as fontes citadas.'
      })}
    </span>
    
    <div className="input-footer-model">
      <ModelSelector compact />
    </div>
  </div>
</div>
```

### 1.2 Comportamento de Altura e Auto-Expansão
* **Altura Padrão em Repouso:** **`44px`** no modo compacto (padding vertical de `5px`, borda de `1px` e altura útil interna de `32px`).
* **Textarea em Linha Única:**
  * `rows={1}`
  * `min-height: 24px`
  * `line-height: 22px`
  * `overflow-y: hidden` por padrão.
* **Comportamento Multilinha (`Shift+Enter` ou colar texto longo):**
  * Auto-expansão baseada em `textarea.scrollHeight`.
  * **Teto Máximo Unificado:** Exatamente **`200px`**. Ao ultrapassar 200px, ativa scrollbar vertical sutil (`scrollbar-width: thin`).
  * Alinhamento vertical do botão `+` e botão de envio: mantêm-se alinhados à parte inferior (`align-self: flex-end`) ao expandir.

---

## 2. Transição Dinâmica de Ações: Voz ➔ Enter (Opção A)

### 2.1 Contrato e Máquina de Estados
Para garantir que o usuário não perca os botões de voz durante o reconhecimento de fala e que o botão Parar realmente cancele o streaming, a renderização segue regras estritas:

```typescript
// Contratos de entrada atualizados
interface Props {
  onSend: (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[]) => void
  onStop?: () => void  // [P1 Resolvido] Contrato explícito para cancelar geração
  isEmpty?: boolean
}
```

```typescript
const isListening = talk.phase === 'listening'
const hasContent = text.trim().length > 0 || attachments.length > 0
```

| Condição | Ação Exibida à Direita | Ícone / Estilo | Comportamento |
| :--- | :--- | :--- | :--- |
| **`isStreaming`** | **Botão Parar Geração** | `Square` (12px preenchido) | Aciona `onStop?.()` (interrompe WebSocket / stream imediatamente). |
| **`isListening`** | **Controles de Voz Ativos** | `Mic` (pulsando) + `AudioLines` | Permanece visível mesmo com transcrição preliminar no campo, permitindo pausar/cancelar. |
| **`!hasContent && !isListening && !isStreaming`** | **Controles de Voz em Repouso** | `Mic` (16px) e `AudioLines` (16px) | Permite iniciar ditado ou loop contínuo de conversa. |
| **`hasContent && !isListening && !isStreaming`** | **Botão de Envio (Opção A)** | **`↵` Enter** (`CornerDownLeft` / glyph ↵) | Envia a mensagem imediatamente para a IA. |

### 2.2 Micro-Transição Visual (Sem Saltos Bruscos)
Os botões à direita são envoltos por um container com transição CSS suave de escala e opacidade (`160ms cubic-bezier(0.16, 1, 0.3, 1)`), garantindo uma transição fluida quando o usuário começa ou para de digitar.

---

## 3. Rodapé Unificado (`input-footer-row`)

* **Posicionamento:** Imediatamente abaixo do card de input, em fluxo natural (fora do card).
* **Layout Flex:** `display: flex; justify-content: space-between; align-items: center; gap: 12px;`
* **Esquerda:** Disclaimer com tipografia leve (`11.5px`), cor `var(--muted-soft)`.
* **Direita:** O pill do `ModelSelector` alinhado à direita, com altura esguia de `26px - 28px`, preservando o padrão de design do Claude.
* **Em Telas Menores (< 640px):** O disclaimer diminui ou adota elipse, preservando a área de toque do seletor.

---

## 4. Teclas de Atalho e Acessibilidade

* `Enter` (Desktop): Dispara envio da mensagem (`handleSend`).
* `Shift + Enter`: Insere quebra de linha sem enviar, acionando a auto-expansão vertical.
* `Enter` (Mobile): Insere quebra de linha normal (envio exclusivamente via botão de toque).
* `Escape`: Fecha o menu `+` ou o balão de modelos caso estejam abertos.
* **Touch Targets (Mobile):** Todos os botões recebem área mínima de toque de **44px** via pseudo-elementos (`touch-target`), sem inflar a barra visual no desktop.
