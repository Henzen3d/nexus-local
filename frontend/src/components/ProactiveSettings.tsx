import { useEffect, useMemo, useState } from 'react'
import { Sparkles, ToggleLeft, ToggleRight, Ban, Undo2, Moon, BarChart3, BookOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import type { ProactiveCategory, ProactiveSensitivity } from '../types'

// ─── ProactiveSettings — painel do usuário (F4.3) ────────────────────────────
// Toggle principal, sensibilidade, categorias, horário silencioso (preparado
// para notificações nativas — F6; aqui só informativo), tópicos bloqueados com
// "desbloquear" e mini-estatística (30 dias). Tudo com efeito imediato (PUT parcial).

const SENSITIVITIES: ProactiveSensitivity[] = ['low', 'medium', 'high']
const CATEGORIES: ProactiveCategory[] = ['event', 'news', 'product', 'place']

export function ProactiveSettings() {
  const { t } = useTranslation()
  const settings = useStore((s) => s.proactiveSettings)
  const loadProactiveSettings = useStore((s) => s.loadProactiveSettings)
  const updateProactiveSettings = useStore((s) => s.updateProactiveSettings)
  const unblockProactiveTopic = useStore((s) => s.unblockProactiveTopic)
  const [busy, setBusy] = useState<string | null>(null)

  useEffect(() => {
    void loadProactiveSettings()
  }, [loadProactiveSettings])

  const categories = useMemo(() => new Set(settings?.categories || []), [settings?.categories])

  if (!settings) {
    return (
      <div className="enhancer-settings proactive-settings" data-testid="proactive-settings">
        <div className="enhancer-header">
          <Sparkles size={20} />
          <div>
            <h3>{t('proactive.settingsTitle')}</h3>
            <p>{t('proactive.settingsDesc')}</p>
          </div>
        </div>
      </div>
    )
  }

  const run = async (key: string, fn: () => Promise<unknown>) => {
    if (busy) return
    setBusy(key)
    try {
      await fn()
    } finally {
      setBusy(null)
    }
  }

  const toggleEnabled = () =>
    run('enabled', () => updateProactiveSettings({ enabled: !settings.enabled }))

  const setSensitivity = (value: ProactiveSensitivity) =>
    run(`sens-${value}`, () => updateProactiveSettings({ sensitivity: value }, { silent: true }))

  const toggleCategory = (cat: ProactiveCategory) => {
    const next = CATEGORIES.filter((c) => (c === cat ? !categories.has(c) : categories.has(c)))
    if (next.length === 0) return // pelo menos uma categoria
    void run(`cat-${cat}`, () => updateProactiveSettings({ categories: next }, { silent: true }))
  }

  const stats = settings.stats
  const blocked = settings.blocked_topics || []

  return (
    <div className="enhancer-settings proactive-settings" data-testid="proactive-settings">
      <div className="enhancer-header">
        <Sparkles size={20} />
        <div>
          <h3>{t('proactive.settingsTitle')}</h3>
          <p>{t('proactive.settingsDesc')}</p>
        </div>
      </div>

      {/* Toggle principal */}
      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('proactive.enabled')}</span>
          <small>{settings.enabled ? t('proactive.enabledHint') : t('proactive.disabledHint')}</small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${settings.enabled ? 'on' : 'off'}`}
          onClick={() => void toggleEnabled()}
          disabled={busy === 'enabled'}
          aria-pressed={settings.enabled}
        >
          {settings.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {settings.enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Sensibilidade */}
      <div className="enhancer-field">
        <label>{t('proactive.sensitivity')}</label>
        <div className="proactive-radio-group" role="radiogroup" aria-label={t('proactive.sensitivity')}>
          {SENSITIVITIES.map((value) => {
            const active = settings.sensitivity === value
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={active}
                className={`proactive-radio ${active ? 'active' : ''}`}
                onClick={() => void setSensitivity(value)}
                disabled={!settings.enabled || busy === `sens-${value}`}
              >
                <strong>{t(`proactive.sensitivity${value[0].toUpperCase()}${value.slice(1)}`)}</strong>
                <small>{t(`proactive.sensitivity${value[0].toUpperCase()}${value.slice(1)}Desc`)}</small>
              </button>
            )
          })}
        </div>
        <small className="proactive-field-help">{t('proactive.sensitivityHelp')}</small>
      </div>

      {/* Categorias */}
      <div className="enhancer-field">
        <label>{t('proactive.categoriesLabel')}</label>
        <div className="proactive-chip-row" role="group" aria-label={t('proactive.categoriesLabel')}>
          {CATEGORIES.map((cat) => {
            const on = categories.has(cat)
            return (
              <button
                key={cat}
                type="button"
                className={`proactive-chip ${on ? 'on' : ''}`}
                aria-pressed={on}
                onClick={() => toggleCategory(cat)}
                disabled={!settings.enabled || busy === `cat-${cat}`}
              >
                {t(`proactive.category.${cat}`)}
              </button>
            )
          })}
        </div>
        <small className="proactive-field-help">{t('proactive.categoriesHelp')}</small>
      </div>

      {/* Horário silencioso — preparado para F6 */}
      <div className="enhancer-field">
        <label>{t('proactive.quietHours')}</label>
        <div className="proactive-quiet-row" aria-disabled="true">
          <Moon size={16} aria-hidden="true" />
          <span>{t('proactive.quietHoursNote')}</span>
        </div>
      </div>

      {/* Tópicos bloqueados */}
      <div className="enhancer-field">
        <label>{t('proactive.blockedTopics')}</label>
        {blocked.length === 0 ? (
          <small className="proactive-field-help">{t('proactive.blockedTopicsEmpty')}</small>
        ) : (
          <ul className="proactive-blocked-list">
            {blocked.map((b) => (
              <li key={b.topic_hash} className="proactive-blocked-item">
                <Ban size={14} aria-hidden="true" />
                <span className="proactive-blocked-label" title={b.topic_label}>{b.topic_label}</span>
                <button
                  type="button"
                  className="proactive-action"
                  onClick={() => void run(`unblock-${b.topic_hash}`, () => unblockProactiveTopic(b.topic_hash))}
                  disabled={busy === `unblock-${b.topic_hash}`}
                >
                  <Undo2 size={14} aria-hidden="true" />
                  {t('proactive.unblock')}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Mini-estatística */}
      {stats && (
        <div className="enhancer-field">
          <label>{t('proactive.stats')}</label>
          <div className="proactive-stats-row">
            <div className="proactive-stat">
              <BarChart3 size={14} aria-hidden="true" />
              <strong>{stats.insights_30d}</strong>
              <span>{t('proactive.statsInsights30d')}</span>
            </div>
            <div className="proactive-stat">
              <strong>{stats.delivered_30d}</strong>
              <span>{t('proactive.statsDelivered30d')}</span>
            </div>
            <div className="proactive-stat">
              <strong>{stats.know_more_30d}</strong>
              <span>{t('proactive.statsKnowMore30d')}</span>
            </div>
          </div>
        </div>
      )}

      {/* F5.3.4 — guia curto "para a família" (a versão completa está em docs/guia-assistente-proativo.md) */}
      <details className="proactive-guide" data-testid="proactive-guide">
        <summary>
          <BookOpen size={14} aria-hidden="true" /> {t('proactive.guide.title')}
        </summary>
        <p>{t('proactive.guide.intro')}</p>
        <ol>
          <li>{t('proactive.guide.step1')}</li>
          <li>{t('proactive.guide.step2')}</li>
          <li>{t('proactive.guide.step3')}</li>
          <li>{t('proactive.guide.step4')}</li>
          <li>{t('proactive.guide.step5')}</li>
        </ol>
        <p className="proactive-guide-privacy">{t('proactive.guide.privacy')}</p>
      </details>
    </div>
  )
}
