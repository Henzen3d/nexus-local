import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'

export function ProviderSelector() {
  const { t } = useTranslation()
  const { models, selectedProviderId, selectProvider, loadModels, isStreaming } = useStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  useEffect(() => {
    loadModels()
  }, [loadModels])

  useEffect(() => {
    if (!open || isMobile) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, isMobile])

  useEffect(() => {
    if (!open || isMobile) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, isMobile])

  // Ordem = 1ª aparição na lista de modelos da API
  // (ORDER BY nexuslocal_score DESC, provider_name, display_name).
  // Só entram provedores enabled com ≥1 modelo enabled e chave de API configurada.
  const providers = Array.from(
    new Map(models.map((m) => [m.provider_id, m.provider_name])).entries()
  ).map(([id, name]) => ({ id, name }))

  const selected = providers.find((p) => p.id === selectedProviderId)

  if (providers.length === 0) return null

  const handleSelectProvider = (providerId: string) => {
    if (isStreaming) return
    selectProvider(providerId)
    setOpen(false)
  }

  return (
    <div className="provider-selector" ref={ref}>
      <button
        type="button"
        className="provider-trigger"
        onClick={() => setOpen((o) => !o)}
        disabled={isStreaming}
        aria-expanded={open}
        aria-haspopup={isMobile ? 'dialog' : 'listbox'}
      >
        <span className="provider-trigger-name">
          {selected ? selected.name : t('chat.selectProvider')}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {open && !isMobile && (
        <div className="provider-dropdown" role="listbox">
          {providers.map((prov) => (
            <button
              key={prov.id}
              type="button"
              role="option"
              aria-selected={prov.id === selectedProviderId}
              className={`provider-option ${prov.id === selectedProviderId ? 'selected' : ''}`}
              onClick={() => handleSelectProvider(prov.id)}
            >
              <span className="provider-option-name">{prov.name}</span>
            </button>
          ))}
        </div>
      )}

      <BottomSheet
        open={open && isMobile}
        onClose={() => setOpen(false)}
        title={t('chat.selectProvider')}
      >
        <div className="nl-sheet-list">
          {providers.map((prov) => {
            const isSelected = prov.id === selectedProviderId
            return (
              <button
                key={prov.id}
                type="button"
                className={`nl-sheet-option ${isSelected ? 'selected' : ''}`}
                onClick={() => handleSelectProvider(prov.id)}
              >
                <div className="nl-sheet-option-body">
                  <span className="nl-sheet-option-name">{prov.name}</span>
                </div>
                {isSelected && <Check size={18} className="nl-sheet-option-check" strokeWidth={2.5} />}
              </button>
            )
          })}
        </div>
      </BottomSheet>
    </div>
  )
}
