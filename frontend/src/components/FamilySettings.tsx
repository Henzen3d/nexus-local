import { useEffect, useState } from 'react'
import { Save, Plus, Trash2, Edit2, Wand2, X, Users, Layers, Search, CheckCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { Provider } from '../types'

interface Family {
  id: string
  display_name: string
  description?: string
  members?: Member[]
}

interface Member {
  model_id: string
  fallback_order: number
  display_name?: string
}

interface Suggestion {
  suggested_id: string
  suggested_name: string
  matched_models: { id: string; display_name: string }[]
  already_has_family: boolean
}

export function FamilySettings() {
  const { t } = useTranslation()
  const [families, setFamilies] = useState<Family[]>([])
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [loading, setLoading] = useState(true)
  const [saved, setSaved] = useState(false)

  // Creation state
  const [isCreating, setIsCreating] = useState(false)
  const [newFamilyId, setNewFamilyId] = useState('')
  const [newFamilyName, setNewFamilyName] = useState('')
  const [newFamilyDesc, setNewFamilyDesc] = useState('')

  // Member adding state for each family
  const [addingToFamily, setAddingToFamily] = useState<string | null>(null)
  const [memberModelId, setMemberModelId] = useState('')
  const [memberFallbackOrder, setMemberFallbackOrder] = useState<number>(1)

  const load = async () => {
    try {
      setLoading(true)
      const [fams, provs, suggs] = await Promise.all([
        api.getFamilies(),
        api.getProviders(),
        api.suggestFamilies()
      ])
      
      // Load members for each family
      const famsWithMembers = await Promise.all(
        fams.map(async (f: Family) => {
          const members = await api.getFamilyMembers(f.id)
          return { ...f, members }
        })
      )
      
      setFamilies(famsWithMembers)
      setProviders(provs.filter(p => p.enabled))
      setSuggestions(suggs)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const handleCreateFamily = async () => {
    if (!newFamilyId.trim() || !newFamilyName.trim()) return
    try {
      await api.createFamily({
        id: newFamilyId.trim(),
        display_name: newFamilyName.trim(),
        description: newFamilyDesc.trim() || undefined
      })
      setNewFamilyId('')
      setNewFamilyName('')
      setNewFamilyDesc('')
      setIsCreating(false)
      load()
    } catch (e) {
      console.error("Erro ao criar família", e)
      alert(t('tools.familyCreateError'))
    }
  }

  const handleDeleteFamily = async (id: string) => {
    if (!window.confirm(`Tem certeza que deseja apagar a família ${id}?`)) return
    try {
      await api.deleteFamily(id)
      load()
    } catch (e) {
      console.error(e)
    }
  }

  const handleAddMember = async (familyId: string) => {
    if (!memberModelId) return
    try {
      await api.addFamilyMember(familyId, {
        model_id: memberModelId,
        fallback_order: memberFallbackOrder
      })
      setAddingToFamily(null)
      setMemberModelId('')
      setMemberFallbackOrder(1)
      load()
    } catch (e) {
      console.error(e)
      alert(t('tools.familyAddMemberError'))
    }
  }

  const handleRemoveMember = async (familyId: string, modelId: string) => {
    try {
      await api.removeFamilyMember(familyId, modelId)
      load()
    } catch (e) {
      console.error(e)
    }
  }

  const handleApplySuggestion = async (sugg: Suggestion) => {
    try {
      if (!sugg.already_has_family) {
        await api.createFamily({
          id: sugg.suggested_id,
          display_name: sugg.suggested_name,
          description: "Criada automaticamente pelo assistente."
        })
      }
      
      let currentOrder = 1
      for (const m of sugg.matched_models) {
        await api.addFamilyMember(sugg.suggested_id, {
          model_id: m.id,
          fallback_order: currentOrder++
        })
      }
      load()
    } catch (e) {
      console.error(e)
      alert(t('tools.familySuggestError'))
    }
  }

  if (loading) return <div className="text-muted-soft">{t('toolsSettings.familyLoading')}</div>

  const allModels = providers.flatMap(p => p.models).filter(m => m.enabled)

  return (
    <div className="family-settings">
      <div className="fusion-header" style={{ marginBottom: '24px' }}>
        <Layers size={20} />
        <div>
          <h3>{t('toolsSettings.familySettingsTitle')}</h3>
          <p>{t('toolsSettings.familySettingsDesc')}</p>
        </div>
      </div>

      {/* Suggestions Section */}
      {suggestions.length > 0 && (
        <div className="admin-section" style={{ background: 'rgba(93, 184, 166, 0.05)', padding: '16px', borderRadius: '8px', border: '1px solid rgba(93, 184, 166, 0.2)' }}>
          <h4 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', color: 'var(--cyan)' }}>
            <Wand2 size={16} /> {t('toolsSettings.familySuggestions')}
          </h4>
          <p style={{ fontSize: '12.5px', color: 'var(--muted)', marginBottom: '12px' }}>
            {t('toolsSettings.familySuggestionsDesc')}
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '12px' }}>
            {suggestions.map((sugg) => (
              <div key={sugg.suggested_id} style={{ background: 'var(--surface)', padding: '12px', borderRadius: '6px', border: '1px solid var(--hairline)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                  <div>
                    <h5 style={{ margin: 0, fontSize: '13.5px', fontWeight: 600 }}>{sugg.suggested_name}</h5>
                    <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '2px' }}>{sugg.suggested_id}</div>
                  </div>
                  <button 
                    onClick={() => handleApplySuggestion(sugg)}
                    className="save-btn" 
                    style={{ padding: '4px 10px', fontSize: '11px' }}
                  >
                    {t('toolsSettings.applySuggestion')}
                  </button>
                </div>
                <div style={{ fontSize: '12px', color: 'var(--ink)' }}>
                  {sugg.matched_models.map((m, i) => (
                    <div key={m.id} style={{ padding: '2px 0', borderTop: i > 0 ? '1px solid var(--hairline)' : 'none', display: 'flex', gap: '4px' }}>
                      <span style={{ color: 'var(--muted)' }}>{i+1}.</span> {m.display_name}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Families List */}
      <div className="admin-section" style={{ marginTop: '32px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h4 style={{ fontSize: '15px', fontWeight: 600 }}>{t('toolsSettings.familiesListTitle')}</h4>
          {!isCreating && (
            <button className="sync-btn" onClick={() => setIsCreating(true)} style={{ padding: '6px 12px', fontSize: '12px' }}>
              <Plus size={14} /> {t('toolsSettings.createFamily')}
            </button>
          )}
        </div>

        {isCreating && (
          <div style={{ background: 'var(--surface-soft)', padding: '16px', borderRadius: '8px', border: '1px solid var(--hairline)', marginBottom: '16px' }}>
            <h5 style={{ margin: '0 0 12px 0', fontSize: '13px' }}>{t('toolsSettings.createFamily')}</h5>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '4px' }}>{t('toolsSettings.familyId')}</label>
                <input type="text" value={newFamilyId} onChange={e => setNewFamilyId(e.target.value)} style={{ width: '100%', padding: '6px 10px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: '4px', fontSize: '13px', outline: 'none' }} placeholder="deepseek-r1" />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '4px' }}>{t('toolsSettings.familyName')}</label>
                <input type="text" value={newFamilyName} onChange={e => setNewFamilyName(e.target.value)} style={{ width: '100%', padding: '6px 10px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: '4px', fontSize: '13px', outline: 'none' }} placeholder="DeepSeek R1" />
              </div>
            </div>
            <div>
              <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: 'var(--muted)', marginBottom: '4px' }}>{t('toolsSettings.familyDesc')}</label>
              <input type="text" value={newFamilyDesc} onChange={e => setNewFamilyDesc(e.target.value)} style={{ width: '100%', padding: '6px 10px', background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: '4px', fontSize: '13px', outline: 'none' }} placeholder={t('tools.familyDescPlaceholder')} />
            </div>
            <div style={{ display: 'flex', gap: '8px', marginTop: '16px', justifyContent: 'flex-end' }}>
              <button className="icon-btn" onClick={() => setIsCreating(false)} style={{ padding: '6px 12px', borderRadius: '4px', fontSize: '12px', border: '1px solid var(--hairline)' }}>{t('common.cancel')}</button>
              <button className="save-btn" onClick={handleCreateFamily} style={{ padding: '6px 12px', borderRadius: '4px', fontSize: '12px' }}>{t('common.save')}</button>
            </div>
          </div>
        )}

        {families.length === 0 ? (
          <p className="text-muted-soft" style={{ fontSize: '13px' }}>{t('toolsSettings.familyNoMembers')}</p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {families.map(f => (
              <div key={f.id} style={{ border: '1px solid var(--hairline)', borderRadius: '8px', overflow: 'hidden' }}>
                <div style={{ background: 'var(--surface-soft)', padding: '12px 16px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--hairline)' }}>
                  <div>
                    <h5 style={{ margin: 0, fontSize: '14.5px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {f.display_name} 
                      <span style={{ fontSize: '11px', background: 'var(--surface-card)', padding: '2px 6px', borderRadius: '10px', fontWeight: 400, color: 'var(--muted)' }}>{f.id}</span>
                    </h5>
                    {f.description && <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: 'var(--muted)' }}>{f.description}</p>}
                  </div>
                  <button className="user-delete-btn" onClick={() => handleDeleteFamily(f.id)} title={t('tools.familyDelete')}><Trash2 size={15} /></button>
                </div>
                
                <div style={{ padding: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                    <h6 style={{ margin: 0, fontSize: '12px', textTransform: 'uppercase', color: 'var(--muted)', fontWeight: 600 }}>
                      {t('toolsSettings.fallbackChain', { count: f.members?.length || 0 })}
                    </h6>
                    <button 
                      className="sync-btn" 
                      onClick={() => { setAddingToFamily(f.id); setMemberFallbackOrder((f.members?.length || 0) + 1); }}
                      style={{ padding: '4px 8px', fontSize: '11px', background: 'transparent', border: '1px solid var(--hairline)', color: 'var(--ink)' }}
                    >
                      <Plus size={12} /> {t('toolsSettings.addModel')}
                    </button>
                  </div>

                  {addingToFamily === f.id && (
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', padding: '8px', background: 'var(--surface-cream-strong)', borderRadius: '6px' }}>
                      <select 
                        value={memberModelId} 
                        onChange={(e) => setMemberModelId(e.target.value)}
                        style={{ flex: 1, padding: '6px', fontSize: '12px', borderRadius: '4px', border: '1px solid var(--hairline)' }}
                      >
                        <option value="">{t('toolsSettings.selectEnabledModel')}</option>
                        {allModels.filter(am => !f.members?.some(m => m.model_id === am.id)).map(am => (
                          <option key={am.id} value={am.id}>{am.display_name} ({am.id})</option>
                        ))}
                      </select>
                      <input 
                        type="number" 
                        value={memberFallbackOrder}
                        onChange={(e) => setMemberFallbackOrder(Number(e.target.value))}
                        title={t('tools.familyFallbackOrder')}
                        style={{ width: '60px', padding: '6px', fontSize: '12px', borderRadius: '4px', border: '1px solid var(--hairline)' }}
                      />
                      <button className="save-btn" onClick={() => handleAddMember(f.id)} style={{ padding: '4px 12px', fontSize: '11px' }}>OK</button>
                      <button className="icon-btn" onClick={() => setAddingToFamily(null)}><X size={14} /></button>
                    </div>
                  )}

                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {f.members?.sort((a,b) => a.fallback_order - b.fallback_order).map(m => {
                      const modelInfo = allModels.find(am => am.id === m.model_id)
                      return (
                        <div key={m.model_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', background: 'var(--surface)', borderRadius: '4px', border: '1px solid var(--hairline)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <span style={{ fontSize: '11px', fontWeight: 600, background: 'var(--surface-soft)', width: '20px', height: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '50%', color: 'var(--ink)' }}>
                              {m.fallback_order}
                            </span>
                            <div>
                              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>{m.display_name || modelInfo?.display_name || m.model_id}</div>
                              <div style={{ fontSize: '11px', color: 'var(--muted)' }}>{m.model_id}</div>
                            </div>
                          </div>
                          <button className="icon-btn" style={{ color: 'var(--error)', opacity: 0.7 }} onClick={() => handleRemoveMember(f.id, m.model_id)} title={t('common.remove')}><Trash2 size={14}/></button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
