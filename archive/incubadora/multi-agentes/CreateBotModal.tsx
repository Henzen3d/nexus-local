/**
 * CreateBotModal.tsx — Modal para Criação/Edição de Bots Especialistas (F8.3.4)
 */
import React, { useState } from 'react'
import { X, Bot, Sparkles, Terminal, Shield, Plus } from 'lucide-react'
import { MASCOT_LIST } from '../mascot/mascotProfiles'
import type { ProactiveBot, MascotId } from '../../types'

interface CreateBotModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (bot: Partial<ProactiveBot>) => Promise<void>
  initialData?: ProactiveBot | null
}

const COLOR_PALETTE = [
  '#3B82F6', '#10B981', '#8B5CF6', '#EC4899', '#F59E0B',
  '#06B6D4', '#EF4444', '#6366F1', '#14B8A6', '#84CC16',
]

export const CreateBotModal: React.FC<CreateBotModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initialData,
}) => {
  const [name, setName] = useState(initialData?.name || '')
  const [title, setTitle] = useState(initialData?.title || '')
  const [description, setDescription] = useState(initialData?.description || '')
  const [systemInstructions, setSystemInstructions] = useState(initialData?.system_instructions || '')
  const [colorHex, setColorHex] = useState(initialData?.color_hex || '#3B82F6')
  const [mascotId, setMascotId] = useState<MascotId>((initialData?.mascot_id as MascotId) || 'nex')
  const [computerMode, setComputerMode] = useState<'shared' | 'isolated' | 'sandbox'>(
    initialData?.computer_mode || 'shared'
  )
  const [ambientEnabled, setAmbientEnabled] = useState(initialData?.ambient_enabled !== false)
  const [ambientTopics, setAmbientTopics] = useState(
    initialData?.ambient_rules?.topics?.join(', ') || ''
  )
  const [isSaving, setIsSaving] = useState(false)

  if (!isOpen) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return

    setIsSaving(true)
    try {
      const topics = ambientTopics
        .split(',')
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean)

      await onSave({
        name: name.trim(),
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        system_instructions: systemInstructions.trim() || undefined,
        color_hex: colorHex,
        mascot_id: mascotId,
        computer_mode: computerMode,
        ambient_enabled: ambientEnabled,
        ambient_rules: topics.length > 0 ? { topics } : null,
      })
      onClose()
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="settings-modal-overlay" onClick={onClose}>
      <div
        className="settings-modal"
        onClick={(e) => e.stopPropagation()}
        style={{ maxWidth: 640, width: '92%' }}
      >
        {/* Header */}
        <div className="settings-modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: 8,
                backgroundColor: colorHex,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#fff',
              }}
            >
              <Bot size={18} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '1.15rem' }}>
                {initialData ? 'Editar Bot Especialista' : 'Criar Novo Bot Especialista'}
              </h2>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--ink-muted)' }}>
                Defina as instruções, mascote e permissões de sandbox do agente
              </p>
            </div>
          </div>
          <button type="button" className="settings-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} style={{ padding: '1.25rem', overflowY: 'auto', maxHeight: '72vh' }}>
          {/* Nome e Título */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
                Nome do Bot *
              </label>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Ex: Auditor de Código"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface)',
                  color: 'var(--ink)',
                }}
              />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
                Especialidade / Título
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ex: Análise Estática & Bugs"
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  borderRadius: 8,
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface)',
                  color: 'var(--ink)',
                }}
              />
            </div>
          </div>

          {/* Breve Descrição */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Descrição da Função
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Explique resumidamente o que este bot faz"
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface)',
                color: 'var(--ink)',
              }}
            />
          </div>

          {/* Instruções do Sistema */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Instruções de Personalidade & Prompt do Sistema
            </label>
            <textarea
              rows={4}
              value={systemInstructions}
              onChange={(e) => setSystemInstructions(e.target.value)}
              placeholder="Você é um especialista em... Sempre forneça respostas estruturadas com..."
              style={{
                width: '100%',
                padding: '8px 12px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface)',
                color: 'var(--ink)',
                fontFamily: 'inherit',
                fontSize: '0.85rem',
                resize: 'vertical',
              }}
            />
          </div>

          {/* Mascote Associado & Cor */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Mascote Visual (entre os 32 disponíveis)
            </label>
            <div
              style={{
                display: 'flex',
                gap: 8,
                overflowX: 'auto',
                paddingBottom: 8,
              }}
            >
              {MASCOT_LIST.slice(0, 12).map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => {
                    setMascotId(m.id)
                    setColorHex(m.color)
                  }}
                  style={{
                    padding: '6px 12px',
                    borderRadius: 20,
                    border: mascotId === m.id ? `2px solid ${m.color}` : '1px solid var(--hairline)',
                    background: mascotId === m.id ? 'var(--surface-soft)' : 'transparent',
                    cursor: 'pointer',
                    fontSize: '0.8rem',
                    color: 'var(--ink)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    flexShrink: 0,
                  }}
                >
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      backgroundColor: m.color,
                    }}
                  />
                  {m.name}
                </button>
              ))}
            </div>
          </div>

          {/* Paleta de Cores */}
          <div style={{ marginBottom: '1rem' }}>
            <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, marginBottom: 4 }}>
              Cor Temática do Bot
            </label>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {COLOR_PALETTE.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColorHex(c)}
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    backgroundColor: c,
                    border: colorHex === c ? '3px solid #fff' : 'none',
                    boxShadow: colorHex === c ? '0 0 0 2px var(--primary)' : 'none',
                    cursor: 'pointer',
                  }}
                />
              ))}
            </div>
          </div>

          {/* Sandbox & Acesso a Computador */}
          <div
            style={{
              padding: '1rem',
              borderRadius: 8,
              background: 'var(--surface-soft)',
              border: '1px solid var(--hairline)',
              marginBottom: '1rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Shield size={16} color="var(--primary)" />
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                Modo Sandbox & Computador Dedicado
              </span>
            </div>
            <div style={{ display: 'flex', gap: 12 }}>
              <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="computerMode"
                  value="shared"
                  checked={computerMode === 'shared'}
                  onChange={() => setComputerMode('shared')}
                />
                Navegador Compartilhado
              </label>
              <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="computerMode"
                  value="sandbox"
                  checked={computerMode === 'sandbox'}
                  onChange={() => setComputerMode('sandbox')}
                />
                Sandbox Isolada (nexus_computer)
              </label>
            </div>
          </div>

          {/* Ambient Listening */}
          <div
            style={{
              padding: '1rem',
              borderRadius: 8,
              background: 'var(--surface-soft)',
              border: '1px solid var(--hairline)',
              marginBottom: '1.25rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                Ambient Listening (Ouvir conversas em segundo plano)
              </span>
              <input
                type="checkbox"
                checked={ambientEnabled}
                onChange={(e) => setAmbientEnabled(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
            </div>
            {ambientEnabled && (
              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--ink-muted)', marginBottom: 4 }}>
                  Tópicos / Palavras-chave de ativação (separados por vírgula):
                </label>
                <input
                  type="text"
                  value={ambientTopics}
                  onChange={(e) => setAmbientTopics(e.target.value)}
                  placeholder="Ex: viagem, hotel, passagem, roteiro"
                  style={{
                    width: '100%',
                    padding: '6px 10px',
                    borderRadius: 6,
                    border: '1px solid var(--hairline)',
                    background: 'var(--surface)',
                    color: 'var(--ink)',
                    fontSize: '0.8rem',
                  }}
                />
              </div>
            )}
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
            <button
              type="button"
              className="settings-secondary-btn"
              onClick={onClose}
              disabled={isSaving}
            >
              Cancelar
            </button>
            <button
              type="submit"
              className="settings-primary-btn"
              disabled={isSaving || !name.trim()}
              style={{ backgroundColor: colorHex }}
            >
              {isSaving ? 'Salvando...' : initialData ? 'Salvar Alterações' : 'Criar Bot'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
