import { useState } from 'react'
import { api } from '../api/client'
import type { Provider } from '../types'

export function CreateFamilyUser({ onCreated }: { onCreated: () => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const submit = async () => {
    setError('')
    if (!username.trim() || !password.trim()) {
      setError('Usuário e senha são obrigatórios.')
      return
    }
    setSaving(true)
    try {
      await api.createUser({
        username: username.trim(),
        password: password.trim(),
        email: email.trim() || undefined,
      })
      setUsername('')
      setPassword('')
      setEmail('')
      onCreated()
    } catch (err) {
      console.error(err)
      setError('Não foi possível criar a conta.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="settings-card-section" style={{ padding: '14px', display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '14px' }}>
      <strong style={{ fontSize: '14px' }}>Nova conta da família</strong>
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="usuário" autoComplete="off" />
      <input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="senha inicial" type="password" autoComplete="new-password" />
      <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="e-mail (opcional)" type="email" autoComplete="off" />
      {error && <div className="login-error">{error}</div>}
      <button type="button" className="save-btn" onClick={submit} disabled={saving}>
        {saving ? 'Criando...' : 'Criar conta'}
      </button>
    </div>
  )
}

export function FamilyUserKeys({
  userId,
  providers,
}: {
  userId: string
  providers: Provider[]
}) {
  const [password, setPassword] = useState('')
  const [providerId, setProviderId] = useState(providers[0]?.id || '')
  const [apiKey, setApiKey] = useState('')
  const [note, setNote] = useState('')

  const resetPassword = async () => {
    if (!password.trim()) return
    await api.resetUserPassword(userId, password.trim())
    setPassword('')
    setNote('Senha atualizada.')
  }

  const saveKey = async () => {
    if (!providerId || !apiKey.trim()) return
    await api.setUserProviderKey(userId, providerId, apiKey.trim())
    setApiKey('')
    setNote('Chave salva nesta conta.')
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
      <div style={{ display: 'flex', gap: '6px' }}>
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="nova senha"
          type="password"
          autoComplete="new-password"
          style={{ flex: 1 }}
        />
        <button type="button" className="save-btn" onClick={resetPassword}>Senha</button>
      </div>
      <div style={{ display: 'flex', gap: '6px' }}>
        <select value={providerId} onChange={(e) => setProviderId(e.target.value)} style={{ flex: 1 }}>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <input
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="chave desta pessoa"
          type="password"
          autoComplete="off"
          style={{ flex: 1 }}
        />
        <button type="button" className="save-btn" onClick={saveKey}>Chave</button>
      </div>
      {note && <span style={{ fontSize: '12px', color: 'var(--muted)' }}>{note}</span>}
    </div>
  )
}
