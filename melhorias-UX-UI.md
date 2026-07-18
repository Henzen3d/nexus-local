````markdown
# 🎨 Solicitação de Melhorias de UI/UX - NexusLocal

## Objetivo

Quero que a interface do NexusLocal fique muito mais próxima da experiência visual da primeira referência (Claude), mantendo nossa identidade visual e sem copiar elementos protegidos.

A prioridade é melhorar:

- Hierarquia visual
- Espaçamento
- Tipografia
- Contraste
- Proporções
- Layout inicial da tela

O resultado deve transmitir uma aparência **premium**, limpa, moderna e profissional.

---

# 1. Menu Lateral (Sidebar)

A sidebar atual está muito larga e pesada visualmente.

### Alterações desejadas

- Aumentar aproximadamente **15%** da largura atual.
- Aumentar o espaçamento interno (padding).
- Melhorar o alinhamento entre ícones e textos.
- Diminuir o peso visual das divisórias.
- Melhorar a hierarquia entre:
  - Conversas
  - Favoritos
  - Recentes
  - Configurações
- Os itens devem respirar mais.
- A sidebar deve parecer mais elegante e menos "quadrada".

---

# 2. Paleta de Cores

A segunda versão está utilizando um bege muito intenso.

Quero uma paleta semelhante ao Claude, utilizando tons neutros e quentes.

## Fundo principal

```css
#FCFBF8
```

ou

```css
#FBFAF7
```

## Sidebar

```css
#F7F4EE
```

## Cards

- Fundo branco
- Sombra extremamente suave

## Bordas

```css
rgba(0,0,0,.06)
```

## Hover

Hover extremamente suave.

Evitar mudanças bruscas de cor.

---

# 3. Tipografia

Hoje os textos parecem apagados.

Precisamos melhorar significativamente a legibilidade.

## Cores

Texto principal

```css
#222222
```

Texto secundário

```css
#555555
```

Texto auxiliar

```css
#777777
```

Evitar cinzas muito claros.

---

## Fonte

Utilizar preferencialmente:

- Inter
ou
- Geist

Pesos recomendados:

- Títulos: 600
- Menus: 500
- Texto: 400

---

# 4. Layout Inicial

A tela inicial deve seguir o mesmo conceito do Claude.

Estrutura:

```
Logo

↓

Mensagem de boas-vindas

↓

Caixa de Prompt
```

Tudo centralizado verticalmente.

A tela deve parecer leve e equilibrada.

---

# 5. Caixa de Prompt

Essa é uma das mudanças mais importantes.

Hoje ela permanece fixa no rodapé.

Quero que o comportamento seja igual ao Claude.

## Nova conversa

Quando abrir uma conversa nova:

```
Logo

↓

Mensagem

↓

Prompt
```

Tudo centralizado.

## Após enviar a primeira mensagem

Depois da primeira interação:

- A conversa sobe normalmente.
- A caixa de prompt vai para o rodapé.
- O comportamento passa a ser o padrão de chat.

---

## Aparência da caixa

- Mais larga
- Mais alta
- Mais padding interno
- Cantos mais arredondados
- Aparência premium

---

# 6. Cabeçalho Superior

Hoje existe:

```
Plano Gratuito
```

Quero substituir por:

> ❤️ Apoiar o NexusLocal

Esse botão abrirá futuramente a página SUPPORT.md ou outra URL configurável.

O estilo deve ser semelhante ao botão "Fazer Upgrade" do Claude.

Elegante.

Discreto.

Sem parecer propaganda.

---

# 7. Espaçamentos

Revisar toda a aplicação.

Padronizar utilizando um sistema baseado em múltiplos de 8.

Exemplo:

```
8
16
24
32
40
48
64
```

Eliminar elementos "espremidos".

---

# 8. Sombras

Padronizar todas as sombras.

Exemplo:

```css
box-shadow:
0 6px 24px rgba(0,0,0,.06);
```

Nada exagerado.

---

# 9. Bordas

Padronizar os raios.

Sidebar

```
16px
```

Cards

```
18px
```

Prompt

```
24px
```

Botões

```
12px
```

---

# 10. Lista de Conversas

Melhorar a aparência da lista lateral.

Adicionar:

- Hover suave
- Item ativo destacado
- Melhor alinhamento
- Mais espaçamento vertical
- Hierarquia visual mais clara

---

# 11. Ícones

Padronizar todos os ícones.

Mesmo tamanho.

Mesmo peso visual.

Preferencialmente utilizar:

- Lucide Icons
ou
- Heroicons

---

# 12. Botões

Todos os botões devem compartilhar o mesmo Design System.

Mesmo:

- Border Radius
- Padding
- Hover
- Peso da fonte
- Altura

---

# 13. Micro Animações

Adicionar pequenas animações.

Exemplos:

Hover

150ms

Fade

200ms

Slide

200ms

Sem exageros.

---

# 14. Responsividade

Garantir que:

- Sidebar colapse corretamente.
- Prompt permaneça centralizado.
- Espaçamentos sejam preservados.
- Componentes mantenham a hierarquia visual.

---

# 15. Tema Claro Premium

Toda a interface deve transmitir a sensação de produtos como:

- Claude
- Notion
- Linear
- Raycast
- Arc Browser

Características esperadas:

- Muito espaço em branco
- Excelente contraste
- Leveza visual
- Poucos elementos
- Hierarquia clara
- Aparência sofisticada

---

# 16. Botão "❤️ Apoiar o NexusLocal"

Adicionar um botão no topo da aplicação.

Texto:

```
❤️ Apoiar o NexusLocal
```

Este botão deverá utilizar uma constante de configuração.

Exemplo:

```ts
export const SUPPORT_URL = "https://..."
```

A URL não deve ficar fixa dentro do componente.

Ela será alterada posteriormente para:

- SUPPORT.md
- GitHub Sponsors
- Ko-fi
- Buy Me a Coffee

---

# 17. Revisão Geral

Antes de concluir a implementação, revisar toda a interface procurando:

- Desalinhamentos
- Inconsistências visuais
- Diferenças de padding
- Diferenças de border radius
- Fontes apagadas
- Contraste insuficiente
- Componentes fora do Design System
- Botões com estilos diferentes

Todos os componentes devem seguir uma linguagem visual única.

---

# Resultado Esperado

Ao abrir o NexusLocal, o usuário deve sentir que está utilizando uma aplicação moderna, refinada e premium, inspirada na experiência do Claude, mas com identidade própria.

A interface deve transmitir:

- Elegância
- Leveza
- Excelente legibilidade
- Hierarquia visual clara
- Consistência entre componentes
- Espaçamento equilibrado
- Excelente experiência de uso

O objetivo é que o NexusLocal tenha qualidade visual comparável a aplicações como Claude, Notion, Linear e Raycast, reforçando a percepção de qualidade do projeto open source e preparando a interface para futura monetização através do botão **❤️ Apoiar o NexusLocal**.
````
- 0.1: Gemini 3.5 Flash (Low)
- 0.2: Gemini 3.5 Flash (Low)
- 0.3: Gemini 3.5 Flash (Low)

- 1.1: Gemini 3.1 Pro (Low)
- 1.2: Gemini 3.1 Pro (Low)
- 1.3: Gemini 3.1 Pro (Low)
- 1.4: Gemini 3.1 Pro (Low)

- 2.1: Gemini 3.5 Flash (Low)
- 2.2: Gemini 3.5 Flash (Low)

- 3.1: Gemini 3.1 Pro (Low)
- 3.2: Gemini 3.1 Pro (Low)
- 3.3: Gemini 3.1 Pro (Low)
- 3.4: Gemini 3.1 Pro (Low)
- 3.5: Gemini 3.1 Pro (Low)

- 4.1: Gemini 3.5 Flash (Low)
- 4.2: Gemini 3.5 Flash (Low)
- 4.3: Gemini 3.5 Flash (Low)

- 5.1: Gemini 3.1 Pro (High)
- 5.2: Gemini 3.1 Pro (High)
- 5.3: Gemini 3.1 Pro (High)
- 5.4: Gemini 3.1 Pro (High)

- 6.1: Gemini 3.1 Pro (Low)
- 6.2: Gemini 3.1 Pro (Low)

- 7.1: Gemini 3.5 Flash (Low)

- 8.1: Gemini 3.1 Pro (Low)
- 8.2: Gemini 3.1 Pro (Low)

- 9.1: Gemini 3.5 Flash (Medium)
- 9.2: Gemini 3.5 Flash (Medium)
- 9.3: Gemini 3.5 Flash (Medium)
- 9.4: Gemini 3.5 Flash (Medium)


