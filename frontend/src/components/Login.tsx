import React, { useState } from 'react'
import { Sparkles, ArrowRight, User, Lock, Mail, Phone, Activity } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'

interface LoginProps {
  onLoginSuccess: (token: string, user: { id: string; username: string; email?: string | null; phone?: string | null; role: string }) => void
}

export function Login({ onLoginSuccess }: LoginProps) {
  const { t } = useTranslation()
  const [isRegister, setIsRegister] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [phone, setPhone] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    const nameTrim = username.trim()
    const passTrim = password.trim()
    const emailTrim = email.trim()
    const phoneTrim = phone.trim()

    if (!nameTrim || !passTrim) {
      setError(t('auth.fillRequired'))
      return
    }

    if (isRegister && !emailTrim) {
      setError(t('auth.emailRequired'))
      return
    }

    setLoading(true)
    try {
      if (isRegister) {
        const res = await api.register({ 
          username: nameTrim, 
          password: passTrim,
          email: emailTrim,
          phone: phoneTrim || undefined
        })
        onLoginSuccess(res.token, res.user)
      } else {
        const res = await api.login({ username: nameTrim, password: passTrim })
        onLoginSuccess(res.token, res.user)
      }
    } catch (err: any) {
      console.error(err)
      setError(isRegister ? t('auth.registerError') : t('auth.loginError'))
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

          {isRegister && (
            <>
              <div className="login-input-group">
                <label htmlFor="email">{t('auth.email')}</label>
                <div className="login-input-wrapper">
                  <Mail size={16} className="login-input-icon" />
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={t('auth.emailPlaceholder')}
                    disabled={loading}
                    autoComplete="email"
                  />
                </div>
              </div>

              <div className="login-input-group">
                <label htmlFor="phone">{t('auth.phoneOptional')}</label>
                <div className="login-input-wrapper">
                  <Phone size={16} className="login-input-icon" />
                  <input
                    id="phone"
                    type="text"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    placeholder={t('auth.phonePlaceholder')}
                    disabled={loading}
                    autoComplete="tel"
                  />
                </div>
              </div>
            </>
          )}

          <button type="submit" className="login-submit-btn" disabled={loading}>
            {loading ? (
              <>
                <Activity size={16} className="animate-spin" />
                {t('common.loading')}
              </>
            ) : (
              <>
                {isRegister ? t('auth.createAccount') : t('auth.login')}
                <ArrowRight size={16} />
              </>
            )}
          </button>
        </form>

        <div className="login-toggle">
          <span>
            {isRegister ? t('auth.hasAccount') : t('auth.noAccount')}
          </span>
          <button 
            type="button" 
            onClick={() => {
              setIsRegister(!isRegister)
              setError('')
            }}
            disabled={loading}
          >
            {isRegister ? t('auth.signIn') : t('auth.signUp')}
          </button>
        </div>
      </div>
    </div>
  )
}
