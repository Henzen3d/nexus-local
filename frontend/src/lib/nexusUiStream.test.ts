import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import { scanPartialEnvelope } from './nexusUiStream.ts'

describe('scanPartialEnvelope', () => {
  const fullFence = `Aqui está a sua análise:

\`\`\`nexus-ui
{
  "v": 1,
  "blocks": [
    {
      "id": "c1",
      "type": "chart",
      "title": "Gráfico de Vendas",
      "kind": "bar",
      "x_key": "mes",
      "series": [{"key": "v", "label": "Vendas"}],
      "rows": [{"mes": "Jan", "v": 10}, {"mes": "Fev", "v": 20}]
    },
    {
      "id": "m1",
      "type": "metric",
      "title": "Total do Trimestre",
      "items": [{"label": "Receita", "value": "R$ 30.000"}]
    }
  ]
}
\`\`\`

Qualquer dúvida estou à disposição.`

  it('devolve EMPTY quando não há fence nexus-ui no texto', () => {
    assert.deepEqual(scanPartialEnvelope(''), { blocks: [], pendingType: null, closed: false, found: false })
    assert.deepEqual(scanPartialEnvelope('Olá, tudo bem?'), { blocks: [], pendingType: null, closed: false, found: false })
    assert.deepEqual(scanPartialEnvelope('```json\n{"a": 1}\n```'), { blocks: [], pendingType: null, closed: false, found: false })
  })

  it('detecta fence aberto e extrai blocos conforme fecham', () => {
    const fullResult = scanPartialEnvelope(fullFence)
    assert.equal(fullResult.found, true)
    assert.equal(fullResult.closed, true)
    assert.equal(fullResult.blocks.length, 2)
    assert.equal((fullResult.blocks[0] as any).id, 'c1')
    assert.equal((fullResult.blocks[1] as any).id, 'm1')
    assert.equal(fullResult.pendingType, null)
  })

  it('extrai pendingType quando bloco abriu mas ainda não fechou', () => {
    const partial = `Aqui está:

\`\`\`nexus-ui
{
  "v": 1,
  "blocks": [
    {
      "id": "c1",
      "type": "chart",
      "title": "Gráfico em construção"`

    const res = scanPartialEnvelope(partial)
    assert.equal(res.found, true)
    assert.equal(res.closed, false)
    assert.equal(res.blocks.length, 0)
    assert.equal(res.pendingType, 'chart')
  })

  it('quando 1 bloco fechou e o segundo está em andamento', () => {
    const partial = `Aqui está:

\`\`\`nexus-ui
{
  "v": 1,
  "blocks": [
    {
      "id": "c1",
      "type": "chart",
      "title": "Gráfico Completo",
      "kind": "bar",
      "x_key": "x",
      "series": [{"key": "v"}],
      "rows": [{"x": "a", "v": 1}]
    },
    {
      "id": "m1",
      "type": "metric",
      "title": "Métrica em andamento`

    const res = scanPartialEnvelope(partial)
    assert.equal(res.found, true)
    assert.equal(res.closed, false)
    assert.equal(res.blocks.length, 1)
    assert.equal((res.blocks[0] as any).id, 'c1')
    assert.equal(res.pendingType, 'metric')
  })

  it('não se confunde com chaves } dentro de strings literais', () => {
    const partial = `\`\`\`nexus-ui
{
  "v": 1,
  "blocks": [
    {
      "id": "callout_1",
      "type": "callout",
      "kind": "warning",
      "body": "Cuidado com chaves } e colchetes ] dentro da string! \\"escapes\\""
    }
  ]
}
\`\`\``

    const res = scanPartialEnvelope(partial)
    assert.equal(res.blocks.length, 1)
    assert.equal((res.blocks[0] as any).id, 'callout_1')
    assert.equal(
      (res.blocks[0] as any).body,
      'Cuidado com chaves } e colchetes ] dentro da string! "escapes"'
    )
  })

  it('propriedade de prefixo: nenhum corte quebra ou diverge do resultado final', () => {
    const full = scanPartialEnvelope(fullFence)
    const fullBlocks = full.blocks

    // Testa cortes a cada 5 caracteres ao longo de todo o texto
    for (let i = 1; i <= fullFence.length; i += 5) {
      const slice = fullFence.slice(0, i)
      assert.doesNotThrow(() => {
        const partial = scanPartialEnvelope(slice)
        // O número de blocos parseados no prefixo nunca excede o total
        assert.ok(partial.blocks.length <= fullBlocks.length)
        // Todo bloco parseado no prefixo é estritamente idêntico ao bloco correspondente do final
        for (let k = 0; k < partial.blocks.length; k++) {
          assert.deepEqual(partial.blocks[k], fullBlocks[k])
        }
      })
    }
  })
})
