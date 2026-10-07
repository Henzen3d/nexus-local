import { useSyncExternalStore } from 'react'
import { api } from '../api/client'

export type TtsPrefs = { voice: string; auto: boolean }
export type TtsPlay = { id: string | null; status: 'idle' | 'loading' | 'playing' }

let prefs: TtsPrefs = { voice: 'antonio', auto: false }
let play: TtsPlay = { id: null, status: 'idle' }
let audio: HTMLAudioElement | null = null
let objectUrl: string | null = null
const prefListeners = new Set<() => void>()
const playListeners = new Set<() => void>()
const endedListeners = new Set<(id: string) => void>()

function emitPrefs() {
  prefListeners.forEach((fn) => fn())
}
function emitPlay() {
  playListeners.forEach((fn) => fn())
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

export async function loadTtsPrefs() {
  const data = await api.getTtsSettings()
  prefs = { voice: data.voice || 'antonio', auto: !!data.auto }
  emitPrefs()
  return data
}

export async function saveTtsPrefs(next: Partial<TtsPrefs>) {
  const data = await api.saveTtsSettings(next)
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
  if (audio) {
    audio.onended = null
    audio.pause()
    audio.src = ''
  }
  audio = null
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = null
  play = { id: null, status: 'idle' }
  emitPlay()
}

export async function playSpeech(id: string, text: string, voice = prefs.voice) {
  if (play.id === id && play.status === 'playing') {
    stopSpeech()
    return
  }
  stopSpeech()
  play = { id, status: 'loading' }
  emitPlay()
  try {
    const blob = await api.speak(text, voice)
    if (play.id !== id) return
    objectUrl = URL.createObjectURL(blob)
    audio = new Audio(objectUrl)
    audio.onended = () => {
      if (play.id !== id) return
      stopSpeech()
      endedListeners.forEach((fn) => fn(id))
    }
    await audio.play()
    if (play.id !== id) return
    play = { id, status: 'playing' }
    emitPlay()
  } catch (err) {
    if (play.id === id) stopSpeech()
    throw err
  }
}
