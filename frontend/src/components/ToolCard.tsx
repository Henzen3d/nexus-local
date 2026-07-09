import { Search, Globe, FileText, Terminal, Calculator, Wrench } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type ToolVariant = 'search' | 'browse' | 'read' | 'python' | 'calc' | 'tool'

interface ToolCardProps {
  variant: ToolVariant
  label?: string
  children?: React.ReactNode
}

export function ToolCard({ variant, label, children }: ToolCardProps) {
  const { t } = useTranslation()

  const getVariantConfig = (v: ToolVariant) => {
    switch (v) {
      case 'search': return { icon: <Search size={16} />, defaultLabel: t('admin.searching') }
      case 'browse': return { icon: <Globe size={16} />, defaultLabel: t('admin.navigating') }
      case 'read': return { icon: <FileText size={16} />, defaultLabel: t('admin.readingFile') }
      case 'python': return { icon: <Terminal size={16} />, defaultLabel: t('admin.executingPython') }
      case 'calc': return { icon: <Calculator size={16} />, defaultLabel: t('admin.calculating') }
      case 'tool':
      default: return { icon: <Wrench size={16} />, defaultLabel: t('admin.callingTool') }
    }
  }

  const { icon, defaultLabel } = getVariantConfig(variant)

  return (
    <div className="tool-card">
      <div className="tool-card-header">
        <span className="tool-card-icon">{icon}</span>
        <span className="tool-card-label">{label || defaultLabel}</span>
      </div>
      {children && (
        <div className="tool-card-body">
          {children}
        </div>
      )}
    </div>
  )
}
