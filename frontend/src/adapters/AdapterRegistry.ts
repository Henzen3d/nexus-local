import { ModelAdapter } from './ModelAdapter'
import { GemmaAdapter } from './GemmaAdapter'
import { QwenAdapter } from './QwenAdapter'
import { DeepSeekAdapter } from './DeepSeekAdapter'
import { GenericAdapter } from './GenericAdapter'

/**
 * Registro e Factory Central de Adapters.
 * Escolhe e instancia o adaptador correspondente para cada modelo/provedor.
 */
export class AdapterRegistry {
  /**
   * Obtém o adaptador correto baseado nos IDs de modelo e provedor.
   */
  public static getAdapter(modelId: string | null, providerId: string | null): ModelAdapter {
    const mId = modelId || 'generic'
    const pId = providerId || 'generic'

    const lowerModel = mId.toLowerCase()

    if (lowerModel.includes('gemma')) {
      return new GemmaAdapter(mId, pId)
    }

    if (lowerModel.includes('qwen')) {
      return new QwenAdapter(mId, pId)
    }

    if (lowerModel.includes('deepseek')) {
      return new DeepSeekAdapter(mId, pId)
    }

    // Fallback para qualquer outro modelo
    return new GenericAdapter(mId, pId)
  }
}

