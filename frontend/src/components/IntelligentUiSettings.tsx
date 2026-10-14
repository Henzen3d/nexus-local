import { useEffect, useState } from 'react'
import { LayoutGrid, Save, ToggleLeft, ToggleRight, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useStore } from '../store/useStore'
import type { IntelligentUiConfig } from '../types'

/**
 * Configurações → Ferramentas → Interface Inteligente.
 *
 * Liga/desliga os blocos `nexus-ui/1` na bolha e define de quais hosts o cartão
 * pode carregar imagem. Salvar grava na tabela singleton do servidor e passa a
 * valer no próximo turno — sem restart e sem mexer no `.env`.
 */
export function IntelligentUiSettings() {
  const { t } = useTranslation()
  const setIntelligentUiConfig = useStore((s) => s.setIntelligentUiConfig)
  const [config, setConfig] = useState<IntelligentUiConfig | null>(null)
  const [hostsText, setHostsText] = useState('')
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    api
      .getIntelligentUiConfig()
      .then((cfg) => {
        if (!alive) return
        setConfig(cfg)
        setHostsText(cfg.image_hosts.join(', '))
      })
      .catch((err) => console.error('[IntelligentUiSettings load error]', err))
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [])

  const save = async () => {
    if (!config) return
    setError(null)
    try {
      const res = await api.saveIntelligentUiConfig({
        enabled: config.enabled,
        allow_private_http: config.allow_private_http,
        image_hosts: hostsText
          .split(/[,\s]+/)
          .map((h) => h.trim())
          .filter(Boolean),
      })
      setConfig(res.config)
      setHostsText(res.config.image_hosts.join(', '))
      // O chat passa a respeitar a flag/hosts imediatamente, sem recarregar a página
      setIntelligentUiConfig(res.config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('[IntelligentUiSettings save error]', err)
      setError(t('toolsSettings.intelligentUiSaveError', { defaultValue: 'Não foi possível salvar. Tente novamente.' }))
    }
  }

  if (loading || !config) return null

  const sourceLabel =
    config.source === 'db'
      ? t('toolsSettings.intelligentUiSourceDb', { defaultValue: 'definido neste painel' })
      : config.source === 'env'
        ? t('toolsSettings.intelligentUiSourceEnv', { defaultValue: 'vindo do .env do servidor' })
        : t('toolsSettings.intelligentUiSourceDefault', { defaultValue: 'padrão (nunca configurado)' })

  return (
    <div className="enhancer-settings">
      <div className="enhancer-header">
        <LayoutGrid size={20} />
        <div>
          <h3>{t('toolsSettings.intelligentUiTitle', { defaultValue: 'Interface Inteligente' })}</h3>
          <p>
            {t('toolsSettings.intelligentUiDesc', {
              defaultValue:
                'Barras de progresso, cartões, gráficos, controles e micro-ferramentas desenhados pelo próprio app a partir de dados estruturados da IA. A prosa continua completa sem eles.',
            })}
          </p>
        </div>
      </div>

      {/* Toggle principal */}
      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.intelligentUiEnable', { defaultValue: 'Ativar blocos visuais nas respostas' })}</span>
          <small>
            {t('toolsSettings.intelligentUiEnableDesc', {
              defaultValue:
                'Desligado, o chat fica idêntico ao de antes: sem catálogo no prompt, sem extração e sem blocos na bolha.',
            })}
          </small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.enabled ? 'on' : 'off'}`}
          onClick={() => setConfig({ ...config, enabled: !config.enabled })}
        >
          {config.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Hosts confiáveis para imagem */}
      <div className="enhancer-field">
        <label htmlFor="iui-image-hosts">
          {t('toolsSettings.intelligentUiImageHosts', { defaultValue: 'Hosts confiáveis para imagens dos cartões' })}
        </label>
        <input
          id="iui-image-hosts"
          type="text"
          value={hostsText}
          placeholder="cdn.exemplo.com, fotos.minhacasa.lan"
          onChange={(e) => setHostsText(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11.5px', marginTop: '4px', display: 'block' }}>
          {t('toolsSettings.intelligentUiImageHostsHint', {
            defaultValue:
              'Separe por vírgula. Anexos do próprio app sempre passam. Qualquer outro https fora desta lista é removido do cartão (a IA não escolhe a lista).',
          })}
        </small>
      </div>

      {/* HTTP privado */}
      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.intelligentUiPrivateHttp', { defaultValue: 'Permitir http:// em IP da rede local / .local' })}</span>
          <small>
            {t('toolsSettings.intelligentUiPrivateHttpDesc', {
              defaultValue: 'Para fotos de câmera, NAS ou impressora 3D da casa (10.x, 192.168.x, 172.16-31.x, *.local).',
            })}
          </small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.allow_private_http ? 'on' : 'off'}`}
          onClick={() => setConfig({ ...config, allow_private_http: !config.allow_private_http })}
        >
          {config.allow_private_http ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.allow_private_http ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 12px',
          background: 'var(--surface-soft)',
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--ink-muted)',
          marginBottom: '16px',
        }}
      >
        <Info size={15} style={{ color: 'var(--cyan)', flexShrink: 0 }} />
        <span>
          {t('toolsSettings.intelligentUiSourceInfo', { defaultValue: 'Valor atual' })}: {sourceLabel}.{' '}
          {t('toolsSettings.intelligentUiSourceHint', {
            defaultValue: 'Depois de salvar aqui, o .env deixa de ser lido para estas opções.',
          })}
        </span>
      </div>

      {error && (
        <p role="alert" style={{ color: 'var(--error)', fontSize: '12.5px', margin: '0 0 12px' }}>
          {error}
        </p>
      )}

      <div className="enhancer-actions">
        <button type="button" className={`save-btn ${saved ? 'saved' : ''}`} onClick={save}>
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>
    </div>
  )
}

export default IntelligentUiSettings
