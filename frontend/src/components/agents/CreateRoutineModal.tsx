/**
 * CreateRoutineModal.tsx — Modal para Criação/Edição de Rotinas Agendadas dos Bots (F8.1.3)
 */
import React, { useState } from 'react'
import { X, Clock, Sparkles, Plus, Calendar, Repeat } from 'lucide-react'
import type { ProactiveBot, ProactiveRoutine } from '../../types'

interface CreateRoutineModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (routine: Partial<ProactiveRoutine>) => Promise<void>
  bots: ProactiveBot[]
  selectedBotId?: string
}

export const CreateRoutineModal: React.FC<CreateRoutineModalProps> = ({
  isOpen,
  onClose,
  onSave,
  bots,
  selectedBotId,
}) => {
  const [name, setName] = useState('')
  const [botId, setBotId] = useState(selectedBotId || (bots[0]?.id ?? ''))
  const [prompt, setPrompt] = useState('')
  const [timingType, setTimingType] = useState<'daily' | 'interval'>('daily')
  const [timingValue, setTimingValue] = useState('09:00')
  const [isSaving, setIsSaving] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !botId || !prompt.trim()) return

    setIsSaving(true)
    try {
      await onSave({
        bot_id: botId,
        name: name.trim(),
        prompt: prompt.trim(),
        timing_type: timingType,
        timing_value: timingValue,
        is_active: true,
      })
      onClose()
    } catch (err) {
      console.error('[CreateRoutineModal] Erro ao salvar rotina:', err)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(4px)',
        zIndex: 2500,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1rem',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 480,
          background: 'var(--surface)',
          borderRadius: 16,
          border: '1px solid var(--hairline)',
          boxShadow: '0 20px 40px rgba(0,0,0,0.4)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cabeçalho */}
        <div
          style={{
            padding: '1.25rem 1.5rem',
            borderBottom: '1px solid var(--hairline)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: 'var(--surface-soft)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                background: 'rgba(59, 130, 246, 0.15)',
                color: 'var(--primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Clock size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.05rem', fontWeight: 600, color: 'var(--ink)' }}>
                Nova Rotina Agendada
              </h3>
              <p style={{ margin: 0, fontSize: '0.78rem', color: 'var(--ink-muted)' }}>
                Agende tarefas autônomas e lembretes para seus bots
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--ink-muted)',
              cursor: 'pointer',
              padding: 4,
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Formulário */}
        <form onSubmit={handleSubmit} style={{ padding: '1.25rem 1.5rem', display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Nome da Rotina */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>
              Nome da Rotina / Lembrete *
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ex: Lembrar de contratar FixBlu ou Monitorar notícias"
              required
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface-soft)',
                color: 'var(--ink)',
                fontSize: '0.85rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Bot Responsável */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>
              Assistente Responsável *
            </label>
            <select
              value={botId}
              onChange={(e) => setBotId(e.target.value)}
              required
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface-soft)',
                color: 'var(--ink)',
                fontSize: '0.85rem',
                outline: 'none',
                boxSizing: 'border-box',
              }}
            >
              {bots.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.name} ({b.title || 'Especialista'})
                </option>
              ))}
            </select>
          </div>

          {/* Tipo de Agendamento */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>
              Tipo de Programação
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                type="button"
                onClick={() => {
                  setTimingType('daily')
                  setTimingValue('09:00')
                }}
                style={{
                  flex: 1,
                  padding: '8px',
                  borderRadius: 8,
                  border: timingType === 'daily' ? '1px solid var(--primary)' : '1px solid var(--hairline)',
                  background: timingType === 'daily' ? 'rgba(59, 130, 246, 0.1)' : 'var(--surface-soft)',
                  color: timingType === 'daily' ? 'var(--primary)' : 'var(--ink-muted)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  cursor: 'pointer',
                }}
              >
                <Calendar size={14} />
                <span>Diário (Horário)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setTimingType('interval')
                  setTimingValue('2h')
                }}
                style={{
                  flex: 1,
                  padding: '8px',
                  borderRadius: 8,
                  border: timingType === 'interval' ? '1px solid var(--primary)' : '1px solid var(--hairline)',
                  background: timingType === 'interval' ? 'rgba(59, 130, 246, 0.1)' : 'var(--surface-soft)',
                  color: timingType === 'interval' ? 'var(--primary)' : 'var(--ink-muted)',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 6,
                  cursor: 'pointer',
                }}
              >
                <Repeat size={14} />
                <span>Intervalo Periódico</span>
              </button>
            </div>
          </div>

          {/* Valor do Agendamento */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>
              {timingType === 'daily' ? 'Horário de Execução Diário (HH:MM)' : 'Frequência do Intervalo'}
            </label>
            {timingType === 'daily' ? (
              <input
                type="time"
                value={timingValue}
                onChange={(e) => setTimingValue(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface-soft)',
                  color: 'var(--ink)',
                  fontSize: '0.85rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            ) : (
              <select
                value={timingValue}
                onChange={(e) => setTimingValue(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface-soft)',
                  color: 'var(--ink)',
                  fontSize: '0.85rem',
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              >
                <option value="30m">A cada 30 minutos</option>
                <option value="1h">A cada 1 hora</option>
                <option value="2h">A cada 2 horas</option>
                <option value="4h">A cada 4 horas</option>
                <option value="6h">A cada 6 horas</option>
                <option value="12h">A cada 12 horas</option>
                <option value="1d">A cada 24 horas (1 dia)</option>
              </select>
            )}
          </div>

          {/* Prompt / Instruções */}
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 600, marginBottom: 4, color: 'var(--ink)' }}>
              Tarefa a Executar / Instrução *
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Ex: Verificar se há atualizações no site https://... e me avisar das novidades."
              rows={3}
              required
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface-soft)',
                color: 'var(--ink)',
                fontSize: '0.85rem',
                outline: 'none',
                resize: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Rodapé / Ações */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 8 }}>
            <button
              type="button"
              onClick={onClose}
              disabled={isSaving}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'transparent',
                color: 'var(--ink)',
                fontSize: '0.82rem',
                cursor: 'pointer',
              }}
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={isSaving || !name.trim() || !prompt.trim()}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: 'none',
                background: 'var(--primary)',
                color: '#fff',
                fontSize: '0.82rem',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                cursor: 'pointer',
                opacity: isSaving ? 0.7 : 1,
              }}
            >
              {isSaving ? <Sparkles size={14} className="spin-slow" /> : <Plus size={14} />}
              <span>{isSaving ? 'Salvando...' : 'Criar Rotina'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
