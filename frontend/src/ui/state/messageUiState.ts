import { create } from 'zustand'
import { evaluateExpression, isExpression } from '../lib/safeMath'

interface MessageUiStore {
  /** Estados dos campos por mensagem: messageId -> { fieldId: value } */
  states: Record<string, Record<string, number | string>>
  setUiValue: (messageId: string, fieldId: string, value: number | string) => void
  setUiValues: (messageId: string, values: Record<string, number | string>) => void
  clearMessage: (messageId: string) => void
}

export const useMessageUiStore = create<MessageUiStore>((set) => ({
  states: {},
  setUiValue: (messageId, fieldId, value) =>
    set((state) => {
      const current = state.states[messageId] || {}
      if (current[fieldId] === value) return state
      return {
        states: {
          ...state.states,
          [messageId]: {
            ...current,
            [fieldId]: value,
          },
        },
      }
    }),
  setUiValues: (messageId, values) =>
    set((state) => {
      const current = state.states[messageId] || {}
      return {
        states: {
          ...state.states,
          [messageId]: {
            ...current,
            ...values,
          },
        },
      }
    }),
  clearMessage: (messageId) =>
    set((state) => {
      if (!state.states[messageId]) return state
      const next = { ...state.states }
      delete next[messageId]
      return { states: next }
    }),
}))

/**
 * Hook para acessar o valor resolvido de um campo que pode ser numérico, literal ou expressão `=...`.
 */
export function useResolvedValue(
  messageId: string | undefined,
  rawValue: unknown
): number | string | undefined | null {
  const values = useMessageUiStore((s) => (messageId ? s.states[messageId] : undefined))

  if (rawValue === undefined || rawValue === null) {
    return rawValue
  }

  if (isExpression(rawValue)) {
    if (!values) {
      return '—'
    }
    const evaluated = evaluateExpression(rawValue, values)
    return evaluated !== null && Number.isFinite(evaluated) ? evaluated : '—'
  }

  return rawValue as number | string
}
