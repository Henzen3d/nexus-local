import { NormalizedResponse } from '../types'
import { ThinkingParser, ParsedStream } from '../utils/ThinkingParser'

/**
 * Classe base abstrata para todos os adaptadores de modelos.
 * Garante que qualquer provedor/modelo implementado adira ao
 * contrato rígido de NormalizedResponse, padronizando a UI.
 */
export abstract class ModelAdapter {
  protected modelId: string
  protected providerId: string

  constructor(modelId: string, providerId: string) {
    this.modelId = modelId
    this.providerId = providerId
  }

  /**
   * Converte a resposta bruta do modelo num formato normalizado estrito.
   * Utiliza por padrão o algoritmo de parser universal (ThinkingParser).
   * Subclasses podem sobrescrever este método para lógicas muito singulares,
   * mas o formato de retorno sempre será NormalizedResponse.
   */
  public parse(content: string): NormalizedResponse {
    const { reasoning, answer, isThinking } = ThinkingParser.parse(content)
    
    // Por padrão o adapter base apenas extrai o texto e raciocínio.
    // Tool calls e metadata devem ser preenchidos pelas implementações específicas caso suportem
    return {
      reasoning,
      answer,
      isThinking
    }
  }

  /**
   * Método abstrato opcional (dependendo de como os adapters consumirão fluxos reais futuramente)
   * que processa a saída completa (raw) em NormalizedResponse
   */
  public abstract processCompleteResponse(rawResponse: any): NormalizedResponse
}
