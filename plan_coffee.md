# Plano: Apoio voluntário ao NexusLocal (“Me pague um café”)

## Contexto

O NexusLocal será disponibilizado como **open source no GitHub** e divulgado via **YouTube**. O objetivo é permitir que usuários que se sentirem ajudados possam apoiar o desenvolvimento com doações voluntárias (estilo *Buy Me a Coffee*), com **alcance global** — em especial nos mercados cobertos pelas traduções da interface:

| Código | Público |
|--------|---------|
| `pt-BR` | Brasil |
| `en-US` | Estados Unidos / inglês global |
| `es-419` | América Latina (espanhol) |
| `es-ES` | Espanha |
| `fr-FR` | França |
| `de-DE` | Alemanha |
| `ja` | Japão |
| `ko` | Coreia |

**Princípios:**
- Apoio **100% voluntário** — sem paywall e sem bloquear features do app.
- Poucos botões (clareza > quantidade).
- Facilitar o meio de pagamento **local** (ex.: Pix no Brasil, cartão/PayPal no exterior).
- Transparência: o que o apoio financia.

---

## Stack de doação recomendada

### Camada global (obrigatória no lançamento)

| Canal | Função | Notas |
|-------|--------|--------|
| **GitHub Sponsors** | Padrão open source; botão “Sponsor” no repositório | Requer verificação de conta; pode demorar |
| **Ko-fi** *ou* **Buy Me a Coffee** | “Café” one-click para YouTube e público geral | Escolher **uma** das duas no início (evitar confusão) |

**Sugestão de escolha:** **Ko-fi** (flexível, one-time + opcional membership) **+ GitHub Sponsors**.

### Camada regional (alta conversão)

| Público | Meio |
|---------|------|
| **Brasil** | **Pix** (QR + link do banco) — essencial |
| EUA / Europa / ES / FR / DE | Cartão via Sponsors/Ko-fi + **PayPal** (opcional) |
| Japão / Coreia | Cartão internacional via Ko-fi/Sponsors; PayPal ajuda |

### Opcional (só depois de tração)

- Open Collective (transparência de gastos da comunidade)
- Patreon (se houver conteúdo recorrente)
- Stripe Payment Links próprios (“$3 / $5 / $10”)
- Auto top-up não se aplica aqui (é do lado Grok/xAI, não nosso)

---

## Valores sugeridos (“café” global)

| Nível | USD | EUR | BRL (aprox.) |
|-------|-----|-----|----------------|
| Café | 3–5 | 3–5 | 15–25 |
| Pizza / jantar | 10–15 | 10–15 | 40–60 |
| Apoiador forte | 25+ | 25+ | 100+ |

Sempre permitir **valor livre**. Em Pix: “qualquer valor” + exemplos.

---

## Textos curtos multilíngues (copiar/colar)

Usar no README, SUPPORT, YouTube e (opcionalmente) no app.

| Idioma | Texto |
|--------|--------|
| **pt-BR** | Se o NexusLocal te ajudou a rodar IA em casa, considere apoiar o desenvolvimento. Qualquer valor ajuda a manter o projeto e as traduções. |
| **en-US** | If NexusLocal helped you run AI locally at home, consider buying me a coffee. Any amount helps keep the project and translations going. |
| **es-419** | Si NexusLocal te ayudó a usar IA en casa, considera invitarme un café. Cualquier aporte ayuda a mantener el proyecto y las traducciones. |
| **es-ES** | Si NexusLocal te ha ayudado a usar IA en casa, considera invitarme a un café. Cualquier aportación ayuda a mantener el proyecto y las traducciones. |
| **fr-FR** | Si NexusLocal vous a aidé à faire tourner l’IA chez vous, offrez-moi un café. Chaque contribution aide le projet et les traductions. |
| **de-DE** | Wenn NexusLocal dir geholfen hat, KI zu Hause zu nutzen, spendier mir einen Kaffee. Jeder Betrag unterstützt das Projekt und die Übersetzungen. |
| **ja** | NexusLocal が自宅での AI 利用に役立てば、コーヒー 1 杯分の支援をご検討ください。少額でも開発と翻訳の継続に助かります。 |
| **ko** | NexusLocal이 집에서 AI를 쓰는 데 도움이 되었다면 커피 한 잔 후원을 고려해 주세요. 작은 금액도 프로젝트와 번역 유지에 도움이 됩니다. |

**Tom no YouTube (final do vídeo, ~10–15 s):**  
*“Se o projeto te ajudou, tem link de apoio na descrição — café, Pix, o que fizer sentido. Sem pressão.”*

---

## Onde colocar os links

### 1. GitHub
- [ ] `README.md` — seção **Support / Apoiar** (topo ou final, com badges)
- [ ] `.github/FUNDING.yml` — habilita o botão **Sponsor** no repo
- [ ] `SUPPORT.md` (ou `docs/SUPPORT.md`) — página única com todos os meios + textos nos 8 idiomas
- [ ] Bio do perfil GitHub + website do repo apontando para SUPPORT

### 2. YouTube
- [ ] Descrição fixa do canal / de cada vídeo com 1 link canônico (página SUPPORT)
- [ ] Comentário fixado
- [ ] End screen / card “Apoiar o projeto”
- [ ] Evitar 6 URLs soltas; **um link** → página com as opções

### 3. App (opcional, pós-MVP open source)
- [ ] Configurações → item **“Apoiar o NexusLocal”** (abre URL externa)
- [ ] Não bloquear funcionalidades
- [ ] Usar i18n (`settings.support` / `pwa` ou `common.support`) nos 8 locales

### 4. Página canônica
Preferir **um** destes:
- `https://github.com/<user>/<repo>#support` (âncora no README), ou
- `https://github.com/<user>/<repo>/blob/main/SUPPORT.md`, ou
- GitHub Pages / site simples `https://<user>.github.io/nexuslocal/support`

---

## Arquivos a criar no repositório

### `.github/FUNDING.yml` (modelo)

Preencher com os handles reais antes do merge:

```yaml
# .github/FUNDING.yml
github: [SEU_USUARIO_GITHUB]
ko_fi: SEU_HANDLE_KOFI
# buy_me_a_coffee: SEU_HANDLE   # se preferir BMC em vez de Ko-fi
custom:
  - "https://ko-fi.com/SEU_HANDLE"
  # - "https://www.buymeacoffee.com/SEU_HANDLE"
  - "https://URL_DO_SEU_PIX_OU_PAGINA_DE_APOIO"
```

Documentação: https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/displaying-a-sponsor-button-in-your-repository

### `SUPPORT.md` (estrutura sugerida)

```markdown
# Support NexusLocal / Apoiar o NexusLocal

## Why support? / Por quê apoiar?
...

## Ways to support
1. GitHub Sponsors — ...
2. Ko-fi — ...
3. Pix (Brasil) — QR + chave
4. PayPal (opcional) — ...

## Languages (short messages)
[blocos pt-BR, en-US, es-419, es-ES, fr-FR, de-DE, ja, ko]

## What funds are used for
- Tempo de manutenção e releases
- Traduções e documentação
- Infra de demo/domínio (se houver)
- Custos de divulgação (ex.: assets do vídeo)

## Transparency
Apoio voluntário ao software open source. Não compra licença nem features exclusivas.
```

### README — badges (exemplo)

```markdown
## Support

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-ea4aaa?logo=githubsponsors)](https://github.com/sponsors/SEU_USUARIO)
[![Ko-fi](https://img.shields.io/badge/Ko--fi-Support-ff5e5b?logo=ko-fi)](https://ko-fi.com/SEU_HANDLE)
```

---

## Aspectos legais e transparência

- [ ] Deixar explícito: **doação voluntária**, não venda de licença.
- [ ] Separar, se possível, chave Pix / conta de recebimento do uso pessoal do dia a dia.
- [ ] No Brasil: doações recorrentes ou volume relevante podem ser **renda** — avaliar declaração (contador se crescer).
- [ ] Listar no SUPPORT no que o dinheiro é gasto (mesmo que seja só “tempo de dev”).
- [ ] Não prometer features exclusivas em troca de café se o discurso for FOSS puro (tiers de sponsor no GitHub são ok se forem simbólicos: nome no README, etc.).

---

## Estratégia de lançamento (GitHub + YouTube)

1. Repo público limpo: README, `LICENSE`, screenshots, `docker compose` / `start` claros.
2. Release `v1.0.0` (ou tag estável) antes do vídeo grande.
3. Vídeo: problema → demo local → multi-idioma → open source → **CTA suave de apoio**.
4. Descrição do vídeo com link SUPPORT + link do repo.
5. Issue templates + “Good first issue” aumentam seriedade e confiança (e doações indiretas).

---

## Próximos passos (checklist executável)

### Fase 0 — Decisão (1 dia)
- [ ] Escolher: **Ko-fi** *ou* **Buy Me a Coffee** (não os dois no início).
- [ ] Definir se **PayPal.me** entra na v1 ou fica para depois.
- [ ] Definir URL canônica de apoio (SUPPORT.md no GitHub é o caminho mais simples).
- [ ] Definir nome público do projeto no GitHub (`nexuslocal` / org / user).

### Fase 1 — Contas e meios de pagamento (1–3 dias)
- [ ] Ativar **GitHub Sponsors** no perfil/conta (completar verificação Stripe/KYC se pedido).
- [ ] Criar perfil **Ko-fi** (ou BMC): foto, bio curta, valores sugeridos, página em inglês + menção a outros idiomas.
- [ ] Criar **Pix** dedicado (chave aleatória ou e-mail do projeto) + QR code PNG em `docs/assets/pix-qr.png` (ou só link do banco).
- [ ] (Opcional) **PayPal.me** com handle limpo.
- [ ] Testar um pagamento real pequeno em cada meio (Sponsors/Ko-fi/Pix) e confirmar recebimento.

### Fase 2 — Artefatos no repositório (1 dia)
- [ ] Criar `.github/FUNDING.yml` com handles reais.
- [ ] Criar `SUPPORT.md` com estrutura acima + textos nos 8 idiomas.
- [ ] Atualizar `README.md` com seção Support + badges + link para SUPPORT.
- [ ] (Opcional) `docs/assets/` com QR Pix e screenshot da página Ko-fi.
- [ ] Commit dedicado: `docs: add funding and support links`.

### Fase 3 — YouTube e divulgação (junto do vídeo)
- [ ] Padronizar bloco da descrição (repo + support + timestamps).
- [ ] Comentário fixado com o mesmo link.
- [ ] Mencionar no final do vídeo (sem insistir).
- [ ] Se houver canal/community post, 1 post “projeto open source + como apoiar”.

### Fase 4 — App (opcional, depois da release open source)
- [ ] Adicionar chave i18n `settings.supportProject` / `settings.supportDesc` nos 8 locales.
- [ ] Em Configurações (mobile + desktop): item que abre `SUPPORT_URL` ou o link do Ko-fi/Sponsors.
- [ ] Constante de config em um único lugar, ex. `frontend/src/config/support.ts`:
  ```ts
  export const SUPPORT_URL = 'https://github.com/USER/REPO/blob/main/SUPPORT.md'
  ```
- [ ] Não exibir na tela de login (evitar sensação de pedágio).

### Fase 5 — Manutenção
- [ ] A cada release notável: agradecer sponsors no GitHub Release notes (se houver).
- [ ] Revisar links a cada 6 meses (Pix, Ko-fi, Sponsors ativos).
- [ ] Se o volume crescer: considerar Open Collective + nota fiscal/MEI conforme necessidade local.

---

## Ordem sugerida de execução

```
1. Criar Ko-fi + Pix
2. Ativar GitHub Sponsors (pode rodar em paralelo; liberação pode demorar)
3. Escrever SUPPORT.md + FUNDING.yml + README
4. Publicar repo / release
5. Gravar e publicar vídeo com CTA
6. (Depois) botão no app
```

---

## Critérios de “pronto para divulgar”

- [ ] Pelo menos **2 meios** funcionando (ex.: Ko-fi + Pix, ou Sponsors + Pix).
- [ ] `FUNDING.yml` válido no default branch.
- [ ] `SUPPORT.md` acessível e com QR/link Pix legível.
- [ ] Um **único link** na descrição do YouTube.
- [ ] README explica o projeto **antes** de pedir apoio (valor primeiro, doação depois).

---

## Fora de escopo deste plano

- Sistema de assinatura pago dentro do NexusLocal.
- Features exclusivas “Pro” atreladas a doação (pode ser produto futuro separado).
- Impostos detalhados por país (apenas alerta genérico).
- Integração de pagamento dentro do backend da aplicação.

---

## Referências úteis

- GitHub Sponsors: https://github.com/sponsors  
- FUNDING.yml: https://docs.github.com/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/displaying-a-sponsor-button-in-your-repository  
- Ko-fi: https://ko-fi.com  
- Buy Me a Coffee: https://www.buymeacoffee.com  

---

## Status

| Item | Estado |
|------|--------|
| Decisão de plataformas | Pendente (usuário) |
| Contas Sponsors / Ko-fi / Pix | Pendente |
| `FUNDING.yml` / `SUPPORT.md` / README | Pendente de implementação |
| CTA no app | Opcional / depois |
| Vídeo YouTube | Pendente de divulgação |

**Próxima ação imediata:** criar contas Ko-fi + Pix e anotar os URLs finais; em seguida pedir implementação dos arquivos `FUNDING.yml`, `SUPPORT.md` e seção no README com esses links.
