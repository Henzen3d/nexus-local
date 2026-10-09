# Intelligent UI — documentação e planos

Pasta de implementação futura. Nada daqui está no ar. A flag `INTELLIGENT_UI_ENABLED` nasce desligada.

O Multi+ continua o frontend atual (React 18, Vite, Zustand). A IA não desenha a tela. Ela manda um JSON pequeno. O app, que já está aberto, desenha com componentes que a gente controla.

## O que esta pasta cobre

Quatro famílias de bloco, mais o contrato que as segura:

1. Indicadores e barras de progresso
2. Cartões e imagens
3. Gráficos
4. Botões, formulários e controles

Fora desta pasta: reescrever o Multi+, painel de artefatos HTML/SVG/código, Thesys, SDK do ChatKit, Apps SDK da OpenAI, iframe, SSE paralelo e JavaScript vindo do modelo.

## Leitura

| Arquivo | Para quê |
|---|---|
| [00-visao-e-spec.md](00-visao-e-spec.md) | Contrato. Leia antes de codar. |
| [01-plano-fundacao.md](01-plano-fundacao.md) | Parser, validador, tabela, flag. Sem isso os outros planos não começam. |
| [02-plano-indicadores.md](02-plano-indicadores.md) | Progresso. Primeiro bloco visível. |
| [03-plano-cartoes-imagens.md](03-plano-cartoes-imagens.md) | Cartão e foto. |
| [04-plano-graficos.md](04-plano-graficos.md) | Gráfico com o Recharts que já está no projeto. |
| [05-plano-controles.md](05-plano-controles.md) | Clique que só faz o que o host permite. |
| [06-criterios-aceite.md](06-criterios-aceite.md) | O que tem de passar antes de ligar a flag. |
| [07-chatkit-referencia.md](07-chatkit-referencia.md) | O que ler no ChatKit. Sem instalar. |

Ordem de execução: 01, depois 02, 03, 04, 05. O 06 acompanha cada fase, não espera o fim.

## Estado

Não implementado. Spec e planos apenas. Site em multi.mob.tec.br não muda até rebuild da imagem, e estes arquivos não entram nesse rebuild.
