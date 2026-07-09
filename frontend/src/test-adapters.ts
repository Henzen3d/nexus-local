import { AdapterRegistry } from './adapters/AdapterRegistry'

console.log("=== INICIANDO TESTE CROSS-MODEL DOS ADAPTERS ===")

// Simulações de resposta crua
const gemmaStream = `Aqui está minha análise da situação.

<think>
Estou avaliando como o Gemma costuma responder.
Pode haver tags ou não, dependendo da versão, mas vamos testar a tag think padrão.
</think>

Esta é a resposta final do Gemma.`

const deepSeekStream = `Uma resposta típica do DeepSeek.
<think>
DeepSeek R1 usa intensamente tags think em toda a sua cadeia de pensamento.
</think>
Resposta final compilada.`

const qwenStream = `Qwen response start.
<thinking>
Qwen often uses thinking tags instead of think. Let's see if the parser handles it.
</thinking>
The answer is 42.`

const gemmaAdapter = AdapterRegistry.getAdapter('gemma-2', 'ollama')
const deepSeekAdapter = AdapterRegistry.getAdapter('deepseek-r1:14b', 'ollama')
const qwenAdapter = AdapterRegistry.getAdapter('qwen2.5:32b', 'ollama')

let pass = true;

console.log("\n--- Testando Gemma Adapter ---")
const gRes = gemmaAdapter.parse(gemmaStream)
console.log("Reasoning:", gRes.reasoning ? "Presente" : "Ausente")
console.log("Answer:", gRes.answer?.substring(0, 50).replace(/\n/g, ' ') + "...")
if (gRes.answer?.includes('<think>')) {
  console.error("FALHA: Tag <think> vazou para o answer no Gemma!")
  pass = false;
}

console.log("\n--- Testando DeepSeek Adapter ---")
const dRes = deepSeekAdapter.parse(deepSeekStream)
console.log("Reasoning:", dRes.reasoning ? "Presente" : "Ausente")
console.log("Answer:", dRes.answer?.substring(0, 50).replace(/\n/g, ' ') + "...")
if (dRes.answer?.includes('<think>')) {
  console.error("FALHA: Tag <think> vazou para o answer no DeepSeek!")
  pass = false;
}

console.log("\n--- Testando Qwen Adapter ---")
const qRes = qwenAdapter.parse(qwenStream)
console.log("Reasoning:", qRes.reasoning ? "Presente" : "Ausente")
console.log("Answer:", qRes.answer?.substring(0, 50).replace(/\n/g, ' ') + "...")
if (qRes.answer?.includes('<thinking>')) {
  console.error("FALHA: Tag <thinking> vazou para o answer no Qwen!")
  pass = false;
}

console.log("\n=== TESTES " + (pass ? "PASSARAM COM SUCESSO" : "FALHARAM") + " ===")
