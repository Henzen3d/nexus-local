# Plano de Implementação — Conversas, Artefatos e Favoritos no Sidebar (NexusLocal)

> Referência visual: telas do claude.ai (`/recents` e `/artifacts`) e o menu de 3 pontos de uma conversa. Este documento assume os tokens já definidos em `DESIGN.md` (seção "Theme Modes" e "Product/Chat App Components") — todo componente novo aqui reutiliza `{theme.*}`, não cores fixas.

---

## 0. Resultado esperado (visão geral)

Nova hierarquia do sidebar, de cima para baixo:

```
Sidebar
├── Logo / wordmark + botão de colapsar
├── + Nova Conversa                    (já existe)
├── Conversas                          (NOVO — item fixo, sempre visível)
├── Artefatos                          (NOVO — item fixo, sempre visível)
├── Favoritos                          (NOVO — seção dinâmica, só aparece com ≥1 item)
│   ├── [conversa favoritada 1]  •••
│   ├── [conversa favoritada 2]  •••
│   └── ...
├── Recentes                           (já existe, comportamento inalterado)
│   ├── [conversa recente 1]  •••
│   └── ...
└── Card do usuário (rodapé)           (já existe)
```

O menu de 3 pontos (`•••`) é o mesmo componente em **Favoritos** e em **Recentes** — só muda o rótulo da primeira opção (Favoritar ↔ Desfavoritar).

---

## Fase 1 — Backend / Modelo de dados

**1.1.** Adicionar à tabela `conversations`:
- `is_favorite: boolean` (default `false`)
- `favorited_at: timestamp | null` (usado para ordenar a seção Favoritos por "favoritado mais recente primeiro")

**1.2.** Endpoint `PATCH /conversations/{id}/favorite` — alterna `is_favorite`, seta/limpa `favorited_at`.

**1.3.** Endpoint `PATCH /conversations/{id}/rename` — recebe `{ title: string }`, valida tamanho máximo (sugestão: 100 caracteres).

**1.4.** Endpoint `DELETE /conversations/{id}` — remove a conversa e suas mensagens associadas (confirmar se é soft delete ou hard delete; recomendo soft delete com `deleted_at` para permitir "desfazer" futuramente, mas não é bloqueante).

**1.5.** Endpoint `GET /conversations` com suporte a:
- `?search=` (busca por título)
- `?filter=` (Todos / Favoritos / outros filtros futuros — mapeia o dropdown "Filtrar por Todos" da tela de referência)
- paginação (`?page=`/`?limit=`) já que o histórico cresce

**1.6.** Endpoint `GET /artifacts` com:
- `?search=`
- retorno incluindo: `title`, `type` (html/código/documento), `updated_at`, `visibility` (Publicado/Privado), `view_count`, `thumbnail` (se aplicável)

---

## Fase 2 — Sidebar: itens fixos "Conversas" e "Artefatos"

**2.1.** Criar variante de componente `sidebar-fixed-nav-item` (extensão de `sidebar-nav-item` do DESIGN.md) — mesma tipografia (`{typography.nav-link}`) e cores (`{theme.text-primary}`, hover `{theme.bg-hover}`), mas **nunca** entra em estado "ativo temporário" como os itens de Recentes — funciona como destino de navegação permanente, com estado "selecionado" persistente (fundo `{theme.bg-hover}` ou `{colors.surface-cream-strong}`/equivalente dark) enquanto a respectiva página estiver aberta.

**2.2.** Posicionar "Conversas" imediatamente abaixo de "+ Nova Conversa", e "Artefatos" imediatamente abaixo de "Conversas" — antes de qualquer seção dinâmica (Favoritos/Recentes).

**2.3.** Ícones: usar um ícone de "balão de conversa" para Conversas e um ícone de "esboço/artefato" para Artefatos — reaproveitar os mesmos ícones já usados no header dessas páginas, se existirem na lib de ícones do projeto.

**2.4.** Clique em "Conversas" ou "Artefatos" **não abre nova aba/rota separada visualmente destoante** — deve renderizar dentro do mesmo shell do app (sidebar permanece fixo, muda apenas a área de conteúdo central), mantendo consistência com o padrão de modal/painel já adotado no plano de Configurações.

---

## Fase 3 — Tela "Conversas" (lista completa)

Baseada na referência (busca + filtro + seleção em massa + lista com timestamp relativo).

**3.1.** Header: título "Conversas" + botão `Filtrar por [Todos ▾]` + botão secundário "Selecionar chats" + botão primário "Novo bate-papo" (canto superior direito).

**3.2.** Campo de busca abaixo do header — filtra a lista conforme digitação (debounce ~300ms), usando `{component.text-input}`.

**3.3.** Lista de conversas: cada linha = título + timestamp relativo à direita ("há 3 horas", "ontem", "20 de jun."). Reutilizar o componente `conversation-list-row` (ver Fase 7) — o mesmo usado nas seções Favoritos/Recentes do sidebar, para manter consistência visual entre os dois contextos.

**3.4.** Modo "Selecionar chats": ao clicar, cada linha ganha um checkbox à esquerda; aparece uma barra de ações em massa (favoritar selecionados / apagar selecionados) fixa no topo ou rodapé da lista.

**3.5.** Clique numa linha (fora do modo de seleção) abre a conversa no canvas central.

**3.6.** Estado vazio: quando não há conversas (ou busca sem resultado), mostrar mensagem + ilustração simples, mantendo o mesmo tom editorial do resto do sistema.

---

## Fase 4 — Tela "Artefatos" (grade)

**4.1.** Header: título "Artefatos" + botão primário "Novo artefato" (canto superior direito).

**4.2.** Campo de busca abaixo do header, mesmo padrão da Fase 3.2.

**4.3.** Grade de cards (3 colunas desktop / 2 tablet / 1 mobile, seguindo os breakpoints já documentados em `DESIGN.md`):
- Preview/thumbnail no topo do card (miniatura renderizada do artefato, ou um placeholder de ícone quando não houver preview disponível)
- Contador de visualizações (ícone de olho + número) no canto do preview, quando houver
- Nome do arquivo/artefato (`{typography.title-sm}`)
- Metadado: "Editado há X" + badge de visibilidade ("Publicado"/"Privado")

**4.4.** Clique no card abre o artefato no editor/visualizador correspondente.

**4.5.** Estado vazio: mesma lógica da Fase 3.6, adaptada para "Nenhum artefato ainda — crie o primeiro".

---

## Fase 5 — Menu de 3 pontos por conversa

**5.1.** Trigger `•••` já existe no hover das linhas de "Recentes" (conforme `sidebar-recent-section` do DESIGN.md) — replicar o mesmo comportamento nas linhas de "Favoritos" e nas linhas da tela "Conversas" (Fase 3.3).

**5.2.** Novo componente `conversation-context-menu` (dropdown):
- Fundo `{theme.bg-card}`, borda `{theme.border}`, `{rounded.lg}`, sombra leve (mesma receita do `chat-model-selector-dropdown`)
- Item 1: **Favoritar** (ou **Desfavoritar**, se já favoritada) — ícone estrela outline/preenchida, chama `PATCH /conversations/{id}/favorite`
- Item 2: **Mudar o nome** — abre edição inline do título (ver 5.3)
- Item 3: **Apagar** — texto em `{colors.error}`, abre modal de confirmação (ver 5.4)
- Hover de cada item: `{theme.bg-hover}`

**5.3.** Renomear: ao clicar, o título da linha vira um `<input>` editável in-place (mesma fonte/tamanho do título original), com foco automático e texto selecionado. `Enter` salva (`PATCH /conversations/{id}/rename`), `Esc` cancela, perda de foco (`blur`) salva automaticamente.

**5.4.** Apagar: modal de confirmação centralizada — "Apagar esta conversa? Essa ação não pode ser desfeita." com botão secundário "Cancelar" e botão destrutivo "Apagar" (fundo `{colors.error}`, texto branco). Nunca apagar direto sem confirmação.

---

## Fase 6 — Seção "Favoritos" no sidebar

**6.1.** Nova seção entre "Artefatos" (fixo) e "Recentes" (dinâmico existente) — **só renderiza se `is_favorite = true` para pelo menos uma conversa**; caso contrário, a seção inteira (label incluso) fica oculta, sem deixar espaço vazio.

**6.2.** Label da seção: "Favoritos", mesmo estilo de `sidebar-recent-section` ("Recentes" hoje) — `{typography.title-sm}`, cor `{theme.text-secondary}`.

**6.3.** Ordenação: `favorited_at DESC` (favoritado mais recentemente aparece primeiro).

**6.4.** Reatividade: favoritar uma conversa a partir de **qualquer lugar** (sidebar Recentes, tela Conversas, ou dentro do próprio chat aberto) deve:
- Inserir imediatamente a conversa em Favoritos (sem reload de página)
- Manter a conversa também visível em Recentes normalmente (não é mutuamente exclusivo — Favoritos é um "pin", não uma remoção de Recentes)

**6.5.** Desfavoritar remove a linha de Favoritos imediatamente (otimista, sem esperar round-trip da API antes de atualizar a UI — reverter em caso de erro).

---

## Fase 7 — Componentes de design (novos, para adicionar ao DESIGN.md)

| Componente | Descrição | Tokens |
|---|---|---|
| `sidebar-fixed-nav-item` | Item fixo "Conversas"/"Artefatos" | `{theme.text-primary}`, hover `{theme.bg-hover}`, estado selecionado persistente |
| `conversation-list-row` | Linha reutilizável (sidebar Favoritos/Recentes + tela Conversas) | título `{typography.nav-link}` ou `{typography.body-md}` conforme contexto, timestamp `{theme.text-secondary}`, `•••` visível só no hover (ou sempre visível na tela Conversas, já que lá não há restrição de espaço) |
| `conversation-context-menu` | Dropdown de 3 pontos | `{theme.bg-card}`, `{theme.border}`, `{rounded.lg}`, item destrutivo em `{colors.error}` |
| `star-icon-toggle` | Ícone de estrela do "Favoritar" | outline `{theme.text-secondary}` quando inativo, preenchido `{colors.accent-amber}` quando ativo |
| `confirm-delete-modal` | Modal de confirmação de exclusão | overlay escuro, card `{theme.bg-card}`, botão destrutivo `{colors.error}` |
| `artifact-card` | Card da grade de Artefatos | `{theme.bg-card}`, `{rounded.lg}`, preview no topo, badge de visibilidade tipo `{component.badge-pill}` |

---

## Fase 8 — QA / Casos de borda

- [ ] Apagar uma conversa favoritada remove ela de **ambas** as seções (Favoritos e Recentes) simultaneamente.
- [ ] Renomear uma conversa que está aberta no momento atualiza o título no header do chat em tempo real, sem precisar recarregar.
- [ ] Títulos longos truncam com reticências (`text-overflow: ellipsis`) + tooltip nativo (`title=""`) mostrando o nome completo no hover.
- [ ] Estados vazios cobertos: 0 conversas, 0 artefatos, 0 favoritos, busca sem resultado.
- [ ] Toda ação destrutiva (Apagar) exige confirmação — sem exceção, mesmo no modo de seleção em massa.
- [ ] Favoritar/desfavoritar funciona igual em: sidebar (hover + `•••`), tela "Conversas" (`•••` na linha), e — se aplicável — dentro do header da conversa aberta.
- [ ] Comportamento responsivo: em mobile, "Conversas" e "Artefatos" fixos continuam acessíveis mesmo com sidebar colapsado (via menu hambúrguer, conforme breakpoints do DESIGN.md).

---

## Ordem de execução sugerida para o dev

1. Fase 1 (backend/dados) — pré-requisito de tudo.
2. Fase 5 (menu de 3 pontos + renomear/apagar) — já existe parcialmente, é a extensão mais barata.
3. Fase 6 (seção Favoritos) — depende só da Fase 1 + 5.
4. Fase 2 (itens fixos no sidebar) — pode ser feito em paralelo com 3/4.
5. Fase 3 e 4 (telas Conversas/Artefatos completas) — maior esforço, podem ir por último sem bloquear o resto.
6. Fase 7 (formalizar componentes no DESIGN.md) — feito incrementalmente conforme cada peça é implementada.
