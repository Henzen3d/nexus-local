import { ModelAdapter } from './ModelAdapter'
import { NormalizedResponse } from '../types'

/**
 * Adaptador para modelos da família Qwen.
 */
export class QwenAdapter extends ModelAdapter {
  constructor(modelId: string, providerId: string) {
    super(modelId, providerId)
  }

  /**
   * Qwen comumente usa tags como <thought> ou <thinking> para reasoning.
   * O ThinkingParser herdado suporta essa identificação por padrão.
   */
  public parse(content: string): NormalizedResponse {
    return super.parse(content)
  }

  public processCompleteResponse(rawResponse: any): NormalizedResponse {
    let text = ''
    if (typeof rawResponse === 'string') {
      text = rawResponse
    } else if (rawResponse?.choices?.[0]?.message?.content) {
      text = rawResponse.choices[0].message.content
    } else if (rawResponse?.message?.content) {
      text = rawResponse.message.content
    } else if (rawResponse?.response) {
      text = rawResponse.response
    }
    return this.parse(text)
  }
}
