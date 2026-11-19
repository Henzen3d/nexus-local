import test from 'node:test'
import assert from 'node:assert/strict'
import {
  classifyRawError,
  stripSensitiveSecrets,
  sanitizeErrorText,
  sanitizeStepDetail,
  sanitizeStepTitle,
  sanitizeProcessStep,
  sanitizeMessage,
} from './sanitization.ts'
import type { Message, ProcessStep } from '../types.ts'

test('stripSensitiveSecrets remove chaves sk-, tokens Bearer e URLs de billing', () => {
  const input = 'Falha com sk-1234567890abcdef e Bearer my_secret_token_abc na url https://orcarouter.com/billing'
  const cleaned = stripSensitiveSecrets(input)
  assert.doesNotMatch(cleaned, /sk-1234567890abcdef/)
  assert.doesNotMatch(cleaned, /my_secret_token_abc/)
  assert.doesNotMatch(cleaned, /https:\/\/orcarouter\.com\/billing/)
  assert.ok(cleaned.includes('[redacted]'))
  assert.ok(cleaned.includes('[link removido]'))
})

test('classifyRawError identifica quota 402 e modelo indisponível 400', () => {
  const quotaErr = '{"error": {"code": "insufficient_user_quota", "message": "err_credit_gate"}}'
  assert.equal(classifyRawError(quotaErr), 'Crédito indisponível no provedor')

  const modelErr = '{"error": "model_unavailable", "detail": "model is currently unavailable"}'
  assert.equal(classifyRawError(modelErr), 'Modelo temporariamente indisponível')

  const rateErr = 'HTTP 429: too_many_requests, rate limit exceeded'
  assert.equal(classifyRawError(rateErr), 'Limite de requisições excedido')

  const timeoutErr = 'HTTP 504: gateway timeout'
  assert.equal(classifyRawError(timeoutErr), 'Tempo limite esgotado')
})

test('sanitizeErrorText sanitiza JSON bruto e URLs sem quebrar formato', () => {
  const rawJson = JSON.stringify({
    error: {
      code: 'insufficient_user_quota',
      message: 'err_credit_gate',
      billing_url: 'https://orcarouter.com/billing',
    },
    status: 402,
  })
  const sanitized = sanitizeErrorText(rawJson)
  assert.equal(sanitized, 'Crédito indisponível no provedor')
  assert.doesNotMatch(sanitized, /\{/)
  assert.doesNotMatch(sanitized, /orcarouter/)
})

test('sanitizeStepDetail normaliza mensagens compostas de failover da cascata', () => {
  const detailOrca =
    'Tentativa anterior falhou (HTTP 402: {"error": {"code": "insufficient_user_quota", "message": "err_credit_gate", "billing": "https://example.com/billing"}}). Alternando para llm7/deepseek-v4.1-flash.'
  const sanitizedOrca = sanitizeStepDetail(detailOrca)
  assert.equal(
    sanitizedOrca,
    'Tentativa anterior falhou (Crédito indisponível no provedor). Alternando para llm7/deepseek-v4.1-flash.'
  )

  const detailLlm7 =
    'Tentativa anterior falhou (HTTP 400: {"error": "model_unavailable"}). Alternando para Nemotron 3 Ultra 550B.'
  const sanitizedLlm7 = sanitizeStepDetail(detailLlm7)
  assert.equal(
    sanitizedLlm7,
    'Tentativa anterior falhou (Modelo temporariamente indisponível). Alternando para Nemotron 3 Ultra 550B.'
  )
})

test('sanitizeProcessStep higieniza título, detalhe e subSteps', () => {
  const step: ProcessStep = {
    id: 'failover-1',
    type: 'tool',
    title: 'Failover: sk-abcdefghij',
    detail: 'Erro https://example.com/account/billing com token Bearer xyz',
    subSteps: ['substep com sk-1234567890'],
    status: 'failed',
  }
  const sanitized = sanitizeProcessStep(step)
  assert.doesNotMatch(sanitized.title, /sk-abcdefghij/)
  assert.doesNotMatch(sanitized.detail || '', /https:\/\/example\.com\/account\/billing/)
  assert.doesNotMatch(sanitized.detail || '', /Bearer xyz/)
  assert.doesNotMatch(sanitized.subSteps?.[0] || '', /sk-1234567890/)
  assert.equal(sanitized.status, 'failed')
})

test('sanitizeMessage preserva chaves sem inventar process_steps undefined', () => {
  const msgWithoutSteps: Message = {
    id: 'msg-1',
    role: 'assistant',
    content: 'Olá! Resposta pronta.',
    created_at: '2026-11-19T20:00:00Z',
  }
  const sanitized = sanitizeMessage(msgWithoutSteps)
  assert.equal('process_steps' in sanitized, false)

  const errorMsg: Message = {
    id: 'err-1',
    role: 'error',
    content: '{"error": {"code": "insufficient_user_quota"}}',
  }
  const sanitizedErr = sanitizeMessage(errorMsg)
  assert.equal(sanitizedErr.content, 'Crédito indisponível no provedor')
})
