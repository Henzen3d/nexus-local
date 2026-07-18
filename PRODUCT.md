# Product

## Register

product

## Platform

web

## Users

Primary audience: **power users of free-tier LLMs** — technical or semi-technical people who already hold API keys (Groq, Gemini, OpenRouter, Cerebras, and peers) and want a local chat surface that keeps history, projects, and orchestration under their control.

Context of use: focused work sessions at a desk or on a phone; configuring providers once, then living in the chat. Secondary surface: self-hosted admins who manage shared keys, users, and quotas for a household or small team.

Job to be done: pick the right free model (or fuse several), get a high-quality answer, keep context across conversations and projects, without locking into a single commercial chat product.

## Product Purpose

NexusLocal is a **local multi-provider chat app** for free and generous free-tier LLMs. It streams replies over WebSockets, stores conversations and settings on-device (SQLite), and layers orchestration features — Prompt Enhancer, Fusion mode, artifacts split-view, web search, and optional local memory — on top of a Claude-like editorial product UI.

Success looks like: a power user can land, add keys, start a conversation with a ranked free model, and trust the chrome (sidebar, composer, themes, mobile shell) enough that the tool disappears into the task.

## Positioning

**Local multi-provider free-tier chat** — one private surface that unifies the best free LLM tiers and orchestration, without a single-vendor lock-in.

## Brand Personality

**Calm, editorial, precise.**

Voice is quiet confidence: short labels, clear verbs, no hype. The product should feel like a carefully typeset tool (cream/coral light, warm charcoal dark) rather than a neon dashboard or a generic SaaS kit. Emotional goal: focus and trust — the user stays in the conversation, not in the chrome.

## Anti-references

- Generic purple SaaS templates and identical icon+card feature grids
- Neon cyberpunk / terminal-only density as the default product voice
- Loud marketing hero patterns inside authenticated app chrome
- Side-stripe “AI card” accents, bounce easings, and decorative glassmorphism
- Copy that says only “Error” / “Loading…” without next step or context

## Design Principles

1. **Tool disappears into the task** — hierarchy and motion serve state change, not spectacle.
2. **One vocabulary everywhere** — same nouns (conversa, modelo, provedor, artefato) and the same button/input shapes across chat, sidebar, and settings.
3. **Progressive power** — free models and basic chat first; Fusion, enhancer, rankings, and admin density reveal on demand.
4. **Local trust** — privacy, keys, and memory language must be plain and accurate; never overclaim.
5. **Ship consistency, not novelty** — reuse tokens (`DESIGN.md` + CSS variables); fix drift at the system, not with one-off colors.

## Accessibility & Inclusion

Target **WCAG AA** for contrast and focus, with **prefers-reduced-motion** respected app-wide. Touch targets minimum **44×44px** on mobile breakpoints. Keyboard focus rings must remain visible (never remove without a replacement). Language is multi-locale via i18n; primary authoring locale is Portuguese (Brazil) with English parity for shared keys.
