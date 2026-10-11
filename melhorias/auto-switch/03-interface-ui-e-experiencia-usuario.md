# 🎨 03. Interface UI & Experiência do Usuário (UI/UX)
**NexusLocal / Multi+** · Especificação Visual e Interações de Front-end

---

## 1. Princípios de Design e Anti-Fricção

A premissa fundamental do Auto-Switch na interface é: **Falhas de infraestrutura de terceiros nunca devem punir o usuário final.**

Quando um modelo falha em um provedor, o software deve:
1. **Resolver silenciosamente:** A resposta deve ser gerada sem interrupção.
2. **Comunicar com transparência sutil:** O usuário deve ser informado de que houve uma troca, mas sem alarmismo ou blocos vermelhos bloqueantes.
3. **Persistir a inteligência:** O seletor de modelos da conversa deve se alinhar automaticamente com o modelo funcional para os próximos turnos.

---

## 2. Componente 1: Badge de Transição Suave na Mensagem

Em vez de renderizar o card de erro vermelho (`chat.generationError`), a mensagem do assistente é entregue normalmente com uma **Pílula de Transição (Failover Pill)** discreta afixada no topo da resposta.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 👤 Você                                                               11:18 │
│ oi                                                                          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│ 🤖 GPT Oss:20b                                                        11:18 │
│                                                                             │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔄 Alternado de Minimax M3 (saldo indisponível · 402) ➔ GPT Oss:20b     │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│ Bom dia, Osmar! Como posso te ajudar hoje?                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1. Anatomia do Badge no CSS/React

```tsx
interface FailoverBadgeProps {
  originalModel: string;
  fallbackModel: string;
  reason: string;
  attempt?: number;
}

export const FailoverBadge: React.FC<FailoverBadgeProps> = ({
  originalModel,
  fallbackModel,
  reason,
}) => {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="failover-pill-container">
      <div 
        className="failover-pill"
        onClick={() => setShowDetails(!showDetails)}
        title="Clique para ver os detalhes da contingência automática"
      >
        <span className="failover-pill-icon">🔄</span>
        <span className="failover-pill-text">
          Alternado de <strong>{originalModel}</strong> ➔ <strong>{fallbackModel}</strong>
        </span>
        <span className="failover-pill-badge">Auto-Switch</span>
      </div>

      {showDetails && (
        <div className="failover-pill-popover">
          <p className="popover-title">Motivo do Redirecionamento:</p>
          <p className="popover-reason">{reason}</p>
          <span className="popover-hint">
            O modelo original foi colocado em contingência para garantir sua resposta contínua.
          </span>
        </div>
      )}
    </div>
  );
};
```

### 2.2. Estilo Visual (Dark/Light Mode Harmonioso)

```css
.failover-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 10px;
  border-radius: 9999px;
  background: var(--surface-soft);
  border: 1px solid var(--hairline);
  font-size: 11px;
  color: var(--ink-secondary);
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.failover-pill:hover {
  background: var(--surface-subtle);
  border-color: var(--primary-accent-tint);
  color: var(--ink);
}

.failover-pill-badge {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  font-weight: 600;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 6px;
}
```

---

## 3. Componente 2: Auto-Alinhamento do Seletor de Modelos

Quando o WebSocket envia o evento `failover_notice` com o novo `fallback_model_id`:

1. O hook [useChat.ts](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/hooks/useChat.ts) intercepta o evento:
   ```typescript
   case 'failover_notice':
     // 1. Atualiza o modelo ativo no estado global da conversa
     s.setCurrentModelId(msg.fallback_model_id);
     // 2. Registra o evento de failover na mensagem atual
     s.setCurrentMessageFailover({
       originalModel: msg.original_model,
       fallbackModel: msg.fallback_model,
       reason: msg.reason,
     });
     // 3. Exibe um toast educativo sutil (apenas na primeira ocorrência)
     s.showToast(`Auto-Switch: alternado para ${msg.fallback_model}`, 'info');
     break;
   ```
2. O seletor de modelos no topo da conversa e o pill do composer atualizam visualmente na mesma hora.
3. A próxima mensagem que o usuário digitar já será enviada para o modelo que está comprovadamente funcionando.

---

## 4. Componente 3: Badges de Saúde no Dropdown de Seleção de Modelos

Ao abrir o seletor de modelos, o usuário visualiza o estado de saúde em tempo real de cada modelo:

```
┌──────────────────────────────────────────────────────────────┐
│ Selecionar Modelo                                           │
├──────────────────────────────────────────────────────────────┤
│ LLM7.io                                                      │
│   🟢 GPT Oss:20b                  128k ctx     [Disponível]  │
│   🟢 GPT-5.4 Mini                 400k ctx     [Disponível]  │
│   🟡 Minimax 2.7                  131k ctx     [Cooldown 8m] │
│   ────────────────────────────────────────────────────────   │
│   👁️ Mostrar modelos desativados (1 oculto: Minimax M3 · 402)│
└──────────────────────────────────────────────────────────────┘
```

### Estados de Saúde:
* 🟢 **Verde (Saudável):** Modelo verificado e respondendo sem erros recentes.
* 🟡 **Amarelo (Cooldown):** Em quarentena temporária devido a erro 400 ou 429. Exibe o tempo restante para liberação automática.
* ⚪ **Oculto / Cinza (Desativado):** Modelos com erro fatal 402/404 não poluem o menu diário. Ficam agrupados em uma seção colapsada para não gerar confusão.

---

## 5. Componente 4: Eliminação de Toasts de Pânico

### Antes:
* Toast vermelho de alta intensidade: `"Erro ao chamar modelo: Provider error 402: ..."`
* Quebrava o fluxo de raciocínio do usuário e exigia troubleshooting manual.

### Depois:
* Se o transbordo obtiver sucesso: **Zero erros vermelhos.** O usuário recebe a resposta formatada com o badge discreto.
* Apenas se **todos os modelos de contingência falharem** (ex: internet do usuário caiu ou o provedor foi desligado por completo), um card de erro amigável é exibido sugerindo outro provedor ativo com 1 clique:
  > *"Não foi possível conectar ao LLM7.io no momento. Deseja tentar com o Groq ou Gemini?" [Tentar com Groq]*
