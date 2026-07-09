import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import ptBR from './locales/pt-BR.json'
import enUS from './locales/en-US.json'
import frFR from './locales/fr-FR.json'
import deDE from './locales/de-DE.json'
import ja from './locales/ja.json'
import ko from './locales/ko.json'
import es419 from './locales/es-419.json'
import esES from './locales/es-ES.json'

export const SUPPORTED_LOCALES = [
  { code: 'pt-BR', nativeName: 'Português (Brasil)' },
  { code: 'en-US', nativeName: 'English (United States)' },
  { code: 'fr-FR', nativeName: 'Français (France)' },
  { code: 'de-DE', nativeName: 'Deutsch (Deutschland)' },
  { code: 'ja', nativeName: '日本語' },
  { code: 'ko', nativeName: '한국어' },
  { code: 'es-419', nativeName: 'Español (Latinoamérica)' },
  { code: 'es-ES', nativeName: 'Español (España)' },
] as const

export type LocaleCode = (typeof SUPPORTED_LOCALES)[number]['code']

const resources = {
  'pt-BR': { translation: ptBR },
  'en-US': { translation: enUS },
  'fr-FR': { translation: frFR },
  'de-DE': { translation: deDE },
  ja: { translation: ja },
  ko: { translation: ko },
  'es-419': { translation: es419 },
  'es-ES': { translation: esES },
}

/** Map browser language tags to our supported codes */
export function mapBrowserLanguage(lang: string | undefined | null): LocaleCode {
  if (!lang) return 'pt-BR'
  const lower = lang.toLowerCase()
  if (lower.startsWith('pt')) return 'pt-BR'
  if (lower.startsWith('en')) return 'en-US'
  if (lower.startsWith('fr')) return 'fr-FR'
  if (lower.startsWith('de')) return 'de-DE'
  if (lower.startsWith('ja')) return 'ja'
  if (lower.startsWith('ko')) return 'ko'
  // Latin America Spanish variants
  if (
    lower === 'es-419' ||
    lower.startsWith('es-mx') ||
    lower.startsWith('es-ar') ||
    lower.startsWith('es-co') ||
    lower.startsWith('es-cl') ||
    lower.startsWith('es-pe') ||
    lower.startsWith('es-ve') ||
    lower.startsWith('es-uy') ||
    lower.startsWith('es-py') ||
    lower.startsWith('es-bo') ||
    lower.startsWith('es-ec') ||
    lower.startsWith('es-gt') ||
    lower.startsWith('es-cr') ||
    lower.startsWith('es-pa') ||
    lower.startsWith('es-do') ||
    lower.startsWith('es-hn') ||
    lower.startsWith('es-sv') ||
    lower.startsWith('es-ni') ||
    lower.startsWith('es-cu') ||
    lower.startsWith('es-pr')
  ) {
    return 'es-419'
  }
  if (lower.startsWith('es')) return 'es-ES'
  return 'pt-BR'
}

export function detectInitialLocale(): LocaleCode {
  try {
    const stored = localStorage.getItem('nexuslocal_locale')
    if (stored && SUPPORTED_LOCALES.some((l) => l.code === stored)) {
      return stored as LocaleCode
    }
  } catch {
    /* ignore */
  }
  if (typeof navigator !== 'undefined') {
    return mapBrowserLanguage(navigator.language)
  }
  return 'pt-BR'
}

export function applyDocumentLang(locale: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
  }
}

const initialLng = typeof window !== 'undefined' ? detectInitialLocale() : 'pt-BR'

i18n.use(initReactI18next).init({
  resources,
  lng: initialLng,
  fallbackLng: 'pt-BR',
  interpolation: { escapeValue: false },
  returnNull: false,
})

if (typeof window !== 'undefined') {
  applyDocumentLang(i18n.language)
  i18n.on('languageChanged', (lng) => applyDocumentLang(lng))
}

export default i18n
