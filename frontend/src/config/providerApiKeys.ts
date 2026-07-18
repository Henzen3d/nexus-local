/**
 * URLs oficiais de cadastro / gerenciamento de API Key por provedor.
 * Usado em Configurações > Provedores e Modelos (botão "+ Obter API Key"
 * e ícone de abrir em nova aba ao lado do nome).
 */
export const PROVIDER_API_KEY_URLS: Record<string, string> = {
  groq: 'https://console.groq.com/keys',
  openrouter: 'https://openrouter.ai/keys',
  gemini: 'https://aistudio.google.com/apikey',
  cerebras: 'https://cloud.cerebras.ai',
  zai: 'https://z.ai/manage-apikey/apikey-list',
  ollama: 'https://ollama.com/settings/keys',
  huggingface: 'https://huggingface.co/settings/tokens',
  cloudflare: 'https://dash.cloudflare.com/profile/api-tokens',
  nvidia: 'https://build.nvidia.com/settings/api-keys',
  sambanova: 'https://cloud.sambanova.ai',
  siliconflow: 'https://cloud.siliconflow.com/account/ak',
  longcat: 'https://longcat.chat',
  freetheai: 'https://freetheai.xyz',
  llm7: 'https://token.llm7.io',
  deepseek: 'https://platform.deepseek.com/api_keys',
  qwen: 'https://home.qwencloud.com/api-keys',
  openai: 'https://platform.openai.com/api-keys',
  together: 'https://api.together.xyz/settings/api-keys',
  mistral: 'https://console.mistral.ai/api-keys',
  cohere: 'https://dashboard.cohere.com/api-keys',
  zenmux: 'https://zenmux.ai/platform/pay-as-you-go',
}

export function getProviderApiKeyUrl(providerId: string): string | undefined {
  return PROVIDER_API_KEY_URLS[providerId]
}
