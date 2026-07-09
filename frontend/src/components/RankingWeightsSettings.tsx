import { useEffect, useState } from 'react'
import { Save, Sliders } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'

export function RankingWeightsSettings() {
  const { t } = useTranslation()
  const [weights, setWeights] = useState({
    weight_quality: 0.5,
    weight_popularity: 0.3,
    weight_usage: 0.2,
    max_expected_usage: 500,
  })
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const data = await api.getRankingWeights()
      if (data) {
        setWeights(data)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    try {
      await api.saveRankingWeights(weights)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error(err)
      alert(t('tools.rankingSaveError'))
    }
  }

  if (loading) return null

  // Helper to ensure values sum to 100% when display
  const total = weights.weight_quality + weights.weight_popularity + weights.weight_usage
  const qPct = Math.round((weights.weight_quality / (total || 1)) * 100)
  const pPct = Math.round((weights.weight_popularity / (total || 1)) * 100)
  const uPct = 100 - qPct - pPct

  return (
    <div className="enhancer-settings" style={{ border: '1px solid var(--hairline)', padding: '16px', borderRadius: '8px', background: 'var(--surface)' }}>
      <div className="enhancer-header" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
        <Sliders size={20} className="text-primary" />
        <div>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600 }}>{t('rankingsView.calibrationTitle')}</h3>
          <p style={{ margin: 0, fontSize: '12.5px', color: 'var(--muted)' }}>
            {t('rankingsView.calibrationDesc')}
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {/* Quality Weight */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
            <span style={{ fontWeight: 500 }}>{t('rankingsView.qualityLabel')}</span>
            <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{qPct}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.weight_quality}
            onChange={(e) => setWeights({ ...weights, weight_quality: parseFloat(e.target.value) })}
            style={{ width: '100%', accentColor: 'var(--primary)' }}
          />
          <p style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px', margin: 0 }}>
            {t('rankingsView.qualityDesc')}
          </p>
        </div>

        {/* Popularity Weight */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
            <span style={{ fontWeight: 500 }}>{t('rankingsView.popularityLabel')}</span>
            <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{pPct}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.weight_popularity}
            onChange={(e) => setWeights({ ...weights, weight_popularity: parseFloat(e.target.value) })}
            style={{ width: '100%', accentColor: 'var(--primary)' }}
          />
          <p style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px', margin: 0 }}>
            {t('rankingsView.popularityDesc')}
          </p>
        </div>

        {/* Usage Weight */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '6px' }}>
            <span style={{ fontWeight: 500 }}>{t('rankingsView.usageLabel')}</span>
            <span style={{ color: 'var(--primary)', fontWeight: 600 }}>{uPct}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={weights.weight_usage}
            onChange={(e) => setWeights({ ...weights, weight_usage: parseFloat(e.target.value) })}
            style={{ width: '100%', accentColor: 'var(--primary)' }}
          />
          <p style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px', margin: 0 }}>
            {t('rankingsView.usageDesc')}
          </p>
        </div>

        {/* Max expected usage */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <label style={{ fontSize: '13px', fontWeight: 500 }}>{t('rankingsView.normalizationTitle')}</label>
          <input
            type="number"
            min="10"
            max="10000"
            value={weights.max_expected_usage}
            onChange={(e) => setWeights({ ...weights, max_expected_usage: parseInt(e.target.value) || 500 })}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--hairline)',
              background: 'var(--surface-soft)',
              color: 'var(--ink)',
              fontSize: '13px',
              outline: 'none',
            }}
          />
          <p style={{ fontSize: '11px', color: 'var(--muted)', margin: 0 }}>
            {t('rankingsView.normalizationDesc')}
          </p>
        </div>

        {/* Action Button */}
        <button
          onClick={save}
          className={`save-btn ${saved ? 'saved' : ''}`}
          style={{
            width: '100%',
            padding: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '8px',
            borderRadius: 'var(--radius-md)',
            background: saved ? 'var(--cyan)' : 'var(--primary)',
            color: '#fff',
            border: 'none',
            fontWeight: 500,
            fontSize: '13px',
            cursor: 'pointer',
            transition: 'background 0.2s',
          }}
        >
          <Save size={14} />
          {saved ? t('tools.weightsCalibrated') : t('tools.applyCalibration')}
        </button>
      </div>
    </div>
  )
}
