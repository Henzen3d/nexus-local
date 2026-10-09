# ChatKit — o que ler, o que não copiar

Referência pedida na nota. Não é dependência. Não entra no `package.json`.

Documentação lida em 2026-10-08: [ChatKit widgets](https://developers.openai.com/api/docs/guides/chatkit-widgets). Ações: [ChatKit actions](https://developers.openai.com/api/docs/guides/chatkit-actions).

## O que a página descreve

Widgets são JSON. O backend serve o JSON. O app desenha. Um clique manda um payload de ação (`onAction`) para o servidor. O servidor decide. Imagem de widget deve ser hospedada pelo backend antes de ser citada na mensagem.

O kit deles é uma árvore aberta. Container (`Card`, `ListView`) e nós (`Box`, `Row`, `Text`, `Title`, `Markdown`, `Select`, `Form`, `Badge`, `Spacer`, `Transition`, e outros). Dá para compor layout livre. O Widget Builder gera esse JSON.

## O que aproveitamos

- Dados de um lado, desenho do outro. É o contrato `nexus-ui/1`.
- Clique não executa string. Vira ação com nome, e o backend é quem autoriza.
- Foto de componente entra como anexo já servido pelo Nexus, não como URL inventada.

## O que não aproveitamos

- Pacote, SDK ou script do ChatKit.
- Árvore livre de nós. `Box` e `Row` deixariam o modelo desenhar tela. O `DynamicRenderer` só conhece cinco cartões.
- Colar JSON do Widget Builder no chat.
- SSE novo. O canal continua o WebSocket que `backend/routers/chat.py` já abre.

Cinco cartões, em `frontend/src/ui/components/`: `ProgressCard`, `ChecklistCard`, `ImageCard`, `ChartCard`, `ControlsCard`.
