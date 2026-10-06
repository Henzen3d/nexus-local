import React, { useState } from 'react'
import { ArrowRight, User, Lock, Activity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'

interface LoginProps {
  onLoginSuccess: (token: string, user: { id: string; username: string; email?: string | null; phone?: string | null; role: string }) => void
}

export function Login({ onLoginSuccess }: LoginProps) {
  const { t } = useTranslation()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const nameTrim = username.trim()
    const passTrim = password.trim()

    if (!nameTrim || !passTrim) {
      setError(t('auth.fillRequired'))
      return
    }

    setLoading(true)
    try {
      const res = await api.login({ username: nameTrim, password: passTrim })
      onLoginSuccess(res.token, res.user)
    } catch (err: any) {
      console.error(err)
      setError(t('auth.loginError'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-brand">
          <div className="login-brand-logo">⬡</div>
          <h1>NexusLocal</h1>
          <p>{t('auth.tagline')}</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          {error && <div className="login-error">{error}</div>}

          <div className="login-input-group">
            <label htmlFor="username">{t('auth.username')}</label>
            <div className="login-input-wrapper">
              <User size={16} className="login-input-icon" />
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder={t('auth.usernamePlaceholder')}
                disabled={loading}
                autoComplete="username"
              />
            </div>
          </div>

          <div className="login-input-group">
            <label htmlFor="password">{t('auth.password')}</label>
            <div className="login-input-wrapper">
              <Lock size={16} className="login-input-icon" />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder={t('auth.passwordPlaceholder')}
                disabled={loading}
                autoComplete="current-password"
              />
            </div>
          </div>

          <button type="submit" className="login-submit-btn" disabled={loading}>
            {loading ? (
              <>
                <Activity size={16} className="animate-spin" />
                {t('common.loading')}
              </>
            ) : (
              <>
                {t('auth.login')}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  )
}
