import { useSyncExternalStore } from 'react'
import { api } from '../api/client'

export type TtsPrefs = { voice: string; auto: boolean }
export type TtsPlay = {
  id: string | null
  status: 'idle' | 'loading' | 'playing'
  progress: number
  cachedIds: Set<string>
}

let prefs: TtsPrefs = { voice: 'antonio', auto: false }
let play: TtsPlay = { id: null, status: 'idle', progress: 0, cachedIds: new Set<string>() }
let audio: HTMLAudioElement | null = null
let currentPlayingId: string | null = null
let abortCtrl: AbortController | null = null
let progressTimer: any = null

const prefListeners = new Set<() => void>()
const playListeners = new Set<() => void>()
const endedListeners = new Set<(id: string) => void>()

// Cache em memória dos áudios sintetizados na sessão atual
const MAX_CACHE_SIZE = 40
const audioCache = new Map<string, { blob: Blob; url: string }>()

function emitPrefs() {
  prefListeners.forEach((fn) => fn())
}
function emitPlay() {
  playListeners.forEach((fn) => fn())
}

function startProgressTimer(textLength: number) {
  if (progressTimer) clearInterval(progressTimer)
  const startTime = performance.now()
  // Estima a duração: base de ~800ms + ~1.1ms por caractere (com mínimo de 1.4s e máximo de 8s)
  const estimatedMs = Math.max(1400, Math.min(8000, 800 + textLength * 1.1))

  progressTimer = setInterval(() => {
    const elapsed = performance.now() - startTime
    const ratio = Math.min(1, elapsed / estimatedMs)
    let p: number
    if (ratio < 1) {
      // Curva desacelerada: sobe rápido e desacelera até ~90%
      p = Math.round(90 * (1 - Math.pow(1 - ratio, 1.8)))
    } else {
      // Passou do tempo estimado: sobe lentamente até 98%
      const extraRatio = Math.min(1, (elapsed - estimatedMs) / 3500)
      p = Math.min(98, Math.round(90 + extraRatio * 8))
    }
    p = Math.max(5, p)
    if (play.status === 'loading' && play.progress !== p) {
      play = { ...play, progress: p }
      emitPlay()
    }
  }, 75)
}

function stopProgressTimer() {
  if (progressTimer) {
    clearInterval(progressTimer)
    progressTimer = null
  }
}

export function getTtsPrefs() {
  return prefs
}
export function subscribeTtsPrefs(fn: () => void) {
  prefListeners.add(fn)
  return () => prefListeners.delete(fn)
}
export function getTtsPlay() {
  return play
}
export function subscribeTtsPlay(fn: () => void) {
  playListeners.add(fn)
  return () => playListeners.delete(fn)
}

export function useTtsPrefs() {
  return useSyncExternalStore(subscribeTtsPrefs, getTtsPrefs)
}
export function useTtsPlay() {
  return useSyncExternalStore(subscribeTtsPlay, getTtsPlay)
}

export function clearAudioCache() {
  stopProgressTimer()
  audioCache.forEach((entry) => URL.revokeObjectURL(entry.url))
  audioCache.clear()
  play = { ...play, cachedIds: new Set(), progress: 0 }
  emitPlay()
}

export async function loadTtsPrefs() {
  const data = await api.getTtsSettings()
  prefs = { voice: data.voice || 'antonio', auto: !!data.auto }
  emitPrefs()
  return data
}

export async function saveTtsPrefs(next: Partial<TtsPrefs>) {
  const data = await api.saveTtsSettings(next)
  if (next.voice && next.voice !== prefs.voice) {
    clearAudioCache()
  }
  prefs = { voice: data.voice || 'antonio', auto: !!data.auto }
  emitPrefs()
  return data
}

export function onSpeechEnded(fn: (id: string) => void) {
  endedListeners.add(fn)
  return () => {
    endedListeners.delete(fn)
  }
}

export function stopSpeech() {
  stopProgressTimer()
  if (abortCtrl) {
    abortCtrl.abort()
    abortCtrl = null
  }
  if (audio) {
    audio.onended = null
    audio.pause()
    audio.currentTime = 0
  }
  audio = null
  currentPlayingId = null
  play = { id: null, status: 'idle', progress: 0, cachedIds: new Set(audioCache.keys()) }
  emitPlay()
}

export async function playSpeech(id: string, text: string, voice = prefs.voice) {
  // Se já está tocando ESTE mesmo id -> interrompe
  if (play.id === id && play.status === 'playing') {
    stopSpeech()
    return
  }
  // Se está aguardando o carregamento DESTE mesmo id -> cancela a geração
  if (play.id === id && play.status === 'loading') {
    stopSpeech()
    return
  }

  // Interrompe qualquer áudio ou requisição anterior
  stopProgressTimer()
  if (abortCtrl) {
    abortCtrl.abort()
    abortCtrl = null
  }
  if (audio) {
    audio.onended = null
    audio.pause()
    audio.currentTime = 0
    audio = null
  }

  // 1. Reutilização instantânea de áudio já gerado em cache (0ms)
  const cached = audioCache.get(id)
  if (cached) {
    currentPlayingId = id
    play = { id, status: 'playing', progress: 100, cachedIds: new Set(audioCache.keys()) }
    emitPlay()

    audio = new Audio(cached.url)
    audio.onended = () => {
      if (currentPlayingId !== id) return
      stopSpeech()
      endedListeners.forEach((fn) => fn(id))
    }
    try {
      await audio.play()
    } catch {
      stopSpeech()
    }
    return
  }

  // 2. Não está no cache: ativa estado de loading com timer de progresso
  abortCtrl = new AbortController()
  currentPlayingId = id
  play = { id, status: 'loading', progress: 5, cachedIds: new Set(audioCache.keys()) }
  emitPlay()
  startProgressTimer(text.length)

  try {
    const blob = await api.speak(text, voice, abortCtrl.signal)
    if (currentPlayingId !== id) return

    stopProgressTimer()
    play = { ...play, progress: 100 }
    emitPlay()

    // Salva no cache da sessão com política LRU
    if (audioCache.size >= MAX_CACHE_SIZE) {
      const oldestKey = audioCache.keys().next().value
      if (oldestKey) {
        const old = audioCache.get(oldestKey)
        if (old) URL.revokeObjectURL(old.url)
        audioCache.delete(oldestKey)
      }
    }
    const url = URL.createObjectURL(blob)
    audioCache.set(id, { blob, url })

    audio = new Audio(url)
    audio.onended = () => {
      if (currentPlayingId !== id) return
      stopSpeech()
      endedListeners.forEach((fn) => fn(id))
    }
    play = { id, status: 'playing', progress: 100, cachedIds: new Set(audioCache.keys()) }
    emitPlay()
    await audio.play()
  } catch (err: any) {
    stopProgressTimer()
    if (err?.name === 'AbortError') return
    if (currentPlayingId === id) stopSpeech()
    throw err
  }
}
