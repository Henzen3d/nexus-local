import { ModelAdapter } from './ModelAdapter'
import { NormalizedResponse, NormalizedMetadata } from '../types'

/**
 * Adaptador para modelos da família Gemma.
 */
export class GemmaAdapter extends ModelAdapter {
  constructor(modelId: string, providerId: string) {
    super(modelId, providerId)
  }

  /**
   * Gemma geralmente não utiliza tags de raciocínio como <think> nativamente.
   * Mas se ele as usar via custom instructions ou fine-tuning, o ThinkingParser herdado tratará.
   * Caso contrário, a resposta bruta inteira será retornada como answer.
   */
  public parse(content: string): NormalizedResponse {
    // Reutiliza o fluxo base
    return super.parse(content)
  }

  /**
   * Processa a resposta completa recebida de uma API de chat.
   * Suporta estruturas padrão da API do Gemma (Ollama, HuggingFace ou OpenAI compatível).
   */
  public processCompleteResponse(rawResponse: any): NormalizedResponse {
    let text = ''
    const metadata: NormalizedMetadata = {
      model_id: this.modelId,
      provider: this.providerId
    }

    if (typeof rawResponse === 'string') {
      text = rawResponse
    } else {
      // Extração de texto
      if (rawResponse?.choices?.[0]?.message?.content) {
        text = rawResponse.choices[0].message.content
        // Metadados padrão OpenAI/v1
        if (rawResponse.usage) {
          metadata.input_tokens = rawResponse.usage.prompt_tokens
          metadata.tokens_generated = rawResponse.usage.completion_tokens
        }
      } else if (rawResponse?.message?.content) {
        text = rawResponse.message.content
        // Metadados padrão Ollama
        if (rawResponse.eval_count !== undefined) {
          metadata.tokens_generated = rawResponse.eval_count
          metadata.input_tokens = rawResponse.prompt_eval_count
          if (rawResponse.eval_duration) {
            metadata.total_time_ms = Math.round(rawResponse.eval_duration / 1000000) // nanoseconds to ms
            if (metadata.tokens_generated && metadata.total_time_ms > 0) {
              metadata.tokens_per_second = Number((metadata.tokens_generated / (metadata.total_time_ms / 1000)).toFixed(2))
            }
          }
        }
      } else if (rawResponse?.response) {
        text = rawResponse.response
      }
    }

    const parsed = this.parse(text)
    parsed.metadata = metadata
    
    console.log('[GemmaAdapter] Metadata extracted:', metadata)
    return parsed
  }
}
