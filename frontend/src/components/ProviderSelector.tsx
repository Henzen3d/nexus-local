import { useState, useRef, useEffect } from 'react'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'

export function ProviderSelector() {
  const { t } = useTranslation()
  const { models, selectedProviderId, selectModel, loadModels, isStreaming } = useStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    loadModels()
  }, [loadModels])

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Unique providers from available models (preserving order of first appearance)
  const providers = Array.from(
    new Map(models.map((m) => [m.provider_id, m.provider_name])).entries()
  ).map(([id, name]) => ({ id, name }))

  const selected = providers.find((p) => p.id === selectedProviderId)

  if (providers.length === 0) return null

  const handleSelectProvider = (providerId: string) => {
    if (isStreaming) return
    const firstModel = models.find((m) => m.provider_id === providerId)
    if (firstModel) {
      selectModel(firstModel.id, providerId)
    }
    setOpen(false)
  }

  return (
    <div className="provider-selector" ref={ref}>
      <button
        className="provider-trigger"
        onClick={() => setOpen((o) => !o)}
        disabled={isStreaming}
      >
        <span className="provider-trigger-name">
          {selected ? selected.name : t('chat.selectProvider')}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {open && (
        <div className="provider-dropdown">
          {providers.map((prov) => (
            <button
              key={prov.id}
              className={`provider-option ${prov.id === selectedProviderId ? 'selected' : ''}`}
              onClick={() => handleSelectProvider(prov.id)}
            >
              <span className="provider-option-name">{prov.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
