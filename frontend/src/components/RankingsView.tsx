import { useEffect, useState } from 'react'
import { Award, Sliders, Search, BarChart3, HelpCircle, Save, Star, ChevronDown, ChevronUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useStore } from '../store/useStore'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
} from 'recharts'

export function RankingsView() {
  const { t } = useTranslation()
  const { models, loadModels } = useStore()
  const [rankings, setRankings] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [savingWeights, setSavingWeights] = useState(false)
  const [weightsSaved, setWeightsSaved] = useState(false)
  const [showAll, setShowAll] = useState(false)
  
  // Weights state (for calibration card)
  const [weights, setWeights] = useState({
    weight_quality: 0.5,
    weight_popularity: 0.3,
    weight_usage: 0.2,
    max_expected_usage: 500,
  })

  const loadData = async () => {
    try {
      setLoading(true)
      const [ranksData, weightsData] = await Promise.all([
        api.getRankings(),
        api.getRankingWeights()
      ])
      setRankings(ranksData || [])
      if (weightsData) {
        setWeights(weightsData)
      }
    } catch (err) {
      console.error('Erro ao carregar dados do ranking:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  // Lookup model display details from store models
  const enrichedRankings = rankings.map((r, index) => {
    const detail = models.find((m) => m.id === r.model_id)
    return {
      ...r,
      rank: index + 1,
      display_name: detail ? detail.display_name : r.model_id,
      provider_name: detail ? detail.provider_name : 'Local / Outro',
    }
  })

  // Filter rankings based on search query
  const filteredRankings = enrichedRankings.filter((r) =>
    r.display_name.toLowerCase().includes(search.toLowerCase()) ||
    r.provider_name.toLowerCase().includes(search.toLowerCase()) ||
    r.model_id.toLowerCase().includes(search.toLowerCase())
  )

  // Limit display to top 6 by default
  const displayedRankings = showAll ? filteredRankings : filteredRankings.slice(0, 6)

  // Top 10 for the chart
  const chartData = enrichedRankings.slice(0, 10).map((r) => ({
    name: r.display_name,
    score: parseFloat(r.nexuslocal_score.toFixed(1)),
    provider: r.provider_name,
  }))

  const handleSaveWeights = async () => {
    try {
      setSavingWeights(true)
      await api.saveRankingWeights(weights)
      setWeightsSaved(true)
      setTimeout(() => setWeightsSaved(false), 2000)
      
      // Recarrega os dados locais e sincroniza a store global para o ModelSelector
      await loadModels()
      
      // Recarrega a tabela de rankings local
      const ranksData = await api.getRankings()
      setRankings(ranksData || [])
    } catch (err) {
      console.error(err)
      alert('Erro ao salvar pesos do ranking.')
    } finally {
      setSavingWeights(false)
    }
  }

  // Weight Percentages
  const total = weights.weight_quality + weights.weight_popularity + weights.weight_usage
  const qPct = Math.round((weights.weight_quality / (total || 1)) * 100)
  const pPct = Math.round((weights.weight_popularity / (total || 1)) * 100)
  const uPct = 100 - qPct - pPct

  if (loading && rankings.length === 0) {
    return <div style={{ color: 'var(--muted-soft)', padding: '20px' }}>{t('rankingsView.loading')}</div>
  }

  return (
    <div className="rankings-view" style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      
      {/* Title & Banner */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
        <Award size={22} className="text-primary" />
        <div>
          <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--ink)' }}>{t('rankingsView.title')}</h3>
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted)' }}>
            {t('rankingsView.desc')}
          </p>
        </div>
      </div>

      {/* Main Grid: Left (Table), Right (Chart + Calibration) */}
      <div className="rankings-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '24px' }}>
        
        {/* LEFT COLUMN: Classified Models Table */}
        <div 
          className="admin-section" 
          style={{ 
            padding: '20px', 
            background: 'var(--surface)', 
            borderRadius: '8px', 
            border: '1px solid var(--hairline)',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Star size={14} className="text-primary" /> {t('rankingsView.generalClassification')}
            </h4>
            <div style={{ position: 'relative', width: '200px' }}>
              <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--muted-soft)' }} />
              <input
                type="text"
                placeholder={t('tools.filterModels')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  width: '100%',
                  padding: '6px 12px 6px 30px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface-cream-strong)',
                  color: 'var(--ink)',
                  fontSize: '12.5px',
                  outline: 'none'
                }}
              />
            </div>
          </div>

          <div style={{ overflowX: 'auto', maxHeight: '520px', overflowY: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--hairline)', textAlign: 'left', color: 'var(--muted)' }}>
                  <th style={{ padding: '8px 10px', fontWeight: 600, width: '60px' }}>{t('rankingsView.tableRank')}</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600 }}>{t('rankingsView.tableModelProvider')}</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'center' }}>{t('rankingsView.tableQuality')}</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'center' }}>{t('rankingsView.tablePopularity')}</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'center' }}>{t('rankingsView.tableUsage')}</th>
                  <th style={{ padding: '8px 10px', fontWeight: 600, textAlign: 'right' }}>{t('rankingsView.tableScore')}</th>
                </tr>
              </thead>
              <tbody>
                {filteredRankings.length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'center', padding: '32px', color: 'var(--muted-soft)' }}>
                      {t('rankingsView.noModelsMatched')}
                    </td>
                  </tr>
                ) : (
                  displayedRankings.map((r) => {
                    // Medal styles
                    let rankDisplay = `#${r.rank}`
                    let rankBg = 'transparent'
                    let rankColor = 'var(--muted)'

                    if (r.rank === 1) {
                      rankDisplay = '🥇 #1'
                      rankBg = 'rgba(217, 119, 6, 0.12)'
                      rankColor = '#d97706'
                    } else if (r.rank === 2) {
                      rankDisplay = '🥈 #2'
                      rankBg = 'rgba(112, 128, 144, 0.12)'
                      rankColor = '#708090'
                    } else if (r.rank === 3) {
                      rankDisplay = '🥉 #3'
                      rankBg = 'rgba(180, 83, 9, 0.12)'
                      rankColor = '#b45309'
                    }

                    // Score tier color
                    let scoreColor = 'var(--muted)'
                    let scoreBg = 'rgba(138, 138, 138, 0.06)'
                    if (r.nexuslocal_score >= 80) {
                      scoreColor = 'var(--primary)'
                      scoreBg = 'rgba(204, 120, 92, 0.08)'
                    } else if (r.nexuslocal_score >= 70) {
                      scoreColor = 'var(--cyan)'
                      scoreBg = 'rgba(93, 184, 166, 0.08)'
                    }

                    return (
                      <tr 
                        key={r.model_id} 
                        style={{ borderBottom: '1px solid var(--hairline)', color: 'var(--ink)', transition: 'background 0.1s' }}
                        className="ranking-row"
                      >
                        {/* Position */}
                        <td style={{ padding: '12px 10px', fontWeight: 600 }}>
                          <span style={{ 
                            padding: '2px 6px', 
                            borderRadius: '4px', 
                            background: rankBg, 
                            color: rankColor, 
                            fontSize: '11px',
                            display: 'inline-block',
                            textAlign: 'center'
                          }}>
                            {rankDisplay}
                          </span>
                        </td>
                        
                        {/* Model / Provider */}
                        <td style={{ padding: '12px 10px' }}>
                          <div style={{ fontWeight: 600, color: 'var(--ink)' }}>{r.display_name}</div>
                          <div style={{ fontSize: '11px', color: 'var(--muted)', textTransform: 'capitalize' }}>
                            {r.provider_name}
                          </div>
                        </td>

                        {/* Quality Score */}
                        <td style={{ padding: '12px 10px', textAlign: 'center', color: 'var(--body)' }}>
                          {r.quality_score?.toFixed(0) || '—'}
                          <div style={{ fontSize: '9.5px', color: 'var(--muted-soft)' }}>
                            +{r.quality_contribution.toFixed(1)}
                          </div>
                        </td>

                        {/* Popularity Rank */}
                        <td style={{ padding: '12px 10px', textAlign: 'center', color: 'var(--body)' }}>
                          {r.popularity_rank ? `#${r.popularity_rank}` : '—'}
                          <div style={{ fontSize: '9.5px', color: 'var(--muted-soft)' }}>
                            +{r.popularity_contribution.toFixed(1)}
                          </div>
                        </td>

                        {/* Local Usage */}
                        <td style={{ padding: '12px 10px', textAlign: 'center', color: 'var(--body)' }}>
                          {r.internal_usage_count}
                          <div style={{ fontSize: '9.5px', color: 'var(--muted-soft)' }}>
                            +{r.usage_contribution.toFixed(1)}
                          </div>
                        </td>

                        {/* Score */}
                        <td style={{ padding: '12px 10px', textAlign: 'right', fontWeight: 700 }}>
                          <span style={{ 
                            padding: '3px 8px', 
                            borderRadius: '4px', 
                            color: scoreColor, 
                            background: scoreBg,
                            border: `1px solid ${scoreBg}` 
                          }}>
                            {r.nexuslocal_score.toFixed(1)}
                          </span>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>

          {filteredRankings.length > 6 && (
            <button
              onClick={() => setShowAll(!showAll)}
              style={{
                alignSelf: 'center',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                padding: '8px 16px',
                borderRadius: 'var(--radius-md)',
                background: 'var(--surface-soft)',
                color: 'var(--ink)',
                border: '1px solid var(--hairline)',
                fontSize: '12.5px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'var(--surface-cream-strong)';
                e.currentTarget.style.borderColor = 'var(--primary)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'var(--surface-soft)';
                e.currentTarget.style.borderColor = 'var(--hairline)';
              }}
            >
              {showAll ? (
                <>
                  <ChevronUp size={14} className="text-primary" /> {t('rankingsView.showLess')}
                </>
              ) : (
                <>
                  <ChevronDown size={14} className="text-primary" /> {t('rankingsView.showAll', { count: filteredRankings.length })}
                </>
              )}
            </button>
          )}
        </div>

        {/* RIGHT COLUMN: Chart & Calibration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          
          {/* Top 10 Bar Chart */}
          <div className="admin-section" style={{ padding: '20px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
            <h4 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
              <BarChart3 size={14} className="text-primary" /> {t('rankingsView.top10ChartTitle')}
            </h4>
            <div style={{ height: '240px', width: '100%' }}>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 15, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" horizontal={false} />
                    <XAxis type="number" stroke="var(--muted)" fontSize={11} domain={[0, 100]} />
                    <YAxis 
                      dataKey="name" 
                      type="category" 
                      stroke="var(--muted)" 
                      fontSize={11} 
                      width={100}
                      tickLine={false}
                    />
                    <RechartsTooltip 
                      cursor={{ fill: 'var(--surface-soft)' }}
                      contentStyle={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: '6px', fontSize: '12px' }}
                      formatter={(val: any) => [`${val} pts`, t('rankingsView.scoreChartLabel')]}
                    />
                    <Bar dataKey="score" fill="var(--primary)" radius={[0, 4, 4, 0]} barSize={14} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted-soft)' }}>
                  {t('rankingsView.noModelsChart')}
                </div>
              )}
            </div>
          </div>

          {/* Calibração de Pesos */}
          <div className="admin-section" style={{ padding: '20px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <Sliders size={18} className="text-primary" />
              <div>
                <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>{t('rankingsView.calibrationTitle')}</h4>
                <p style={{ margin: 0, fontSize: '11.5px', color: 'var(--muted)' }}>
                  {t('rankingsView.calibrationDesc')}
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              
              {/* Quality Range */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12.5px', marginBottom: '4px' }}>
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
              </div>

              {/* Popularity Range */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12.5px', marginBottom: '4px' }}>
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
              </div>

              {/* Internal Usage Range */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12.5px', marginBottom: '4px' }}>
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
              </div>

              {/* Max Expected Usage (Normalization) */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                <label style={{ fontSize: '12.5px', fontWeight: 500 }}>{t('rankingsView.normalizationTitle')}</label>
                <input
                  type="number"
                  min="10"
                  max="5000"
                  value={weights.max_expected_usage}
                  onChange={(e) => setWeights({ ...weights, max_expected_usage: parseInt(e.target.value) || 500 })}
                  style={{
                    width: '100%',
                    padding: '6px 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--hairline)',
                    background: 'var(--surface-cream-strong)',
                    color: 'var(--ink)',
                    fontSize: '12.5px',
                    outline: 'none',
                  }}
                />
                <span style={{ fontSize: '10.5px', color: 'var(--muted-soft)' }}>
                  {t('rankingsView.normalizationDesc')}
                </span>
              </div>

              {/* Save Weights Button */}
              <button
                onClick={handleSaveWeights}
                disabled={savingWeights}
                style={{
                  width: '100%',
                  padding: '8px 12px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '8px',
                  borderRadius: 'var(--radius-md)',
                  background: weightsSaved ? 'var(--cyan)' : 'var(--primary)',
                  color: '#fff',
                  border: 'none',
                  fontWeight: 500,
                  fontSize: '13px',
                  cursor: 'pointer',
                  transition: 'background 0.2s',
                  marginTop: '6px'
                }}
              >
                <Save size={14} />
                {savingWeights ? t('common.saving') : weightsSaved ? t('tools.weightsCalibrated') : t('tools.applyCalibration')}
              </button>

            </div>
          </div>

        </div>

      </div>

    </div>
  )
}
