import { ModelAdapter } from './ModelAdapter'
import { NormalizedResponse } from '../types'

/**
 * Adaptador Genérico fallback para qualquer modelo não mapeado
 * explicitamente na arquitetura.
 */
export class GenericAdapter extends ModelAdapter {
  constructor(modelId: string, providerId: string) {
    super(modelId, providerId)
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
