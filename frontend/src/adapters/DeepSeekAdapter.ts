import { ModelAdapter } from './ModelAdapter'
import { NormalizedResponse } from '../types'

/**
 * Adaptador para modelos da família DeepSeek.
 */
export class DeepSeekAdapter extends ModelAdapter {
  constructor(modelId: string, providerId: string) {
    super(modelId, providerId)
  }

  /**
   * DeepSeek-R1 e similares utilizam primordialmente a tag <think>...</think>
   * para isolar o bloco de raciocínio. O parser base trata isso nativamente.
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
