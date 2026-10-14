/**
 * Núcleo do runtime que roda DENTRO do iframe da cena (plano 13): relógio, agregador de
 * `report()`, laço de frames com try/catch e troca de mensagens com o app.
 *
 * Adaptado de AnswerUI — https://github.com/0xcro3dile/answerui
 * (src/scene/runtime/{index,clock,reporter}.ts), MIT License, Copyright (c) 2026 0xcro3dile.
 * O laço com try/catch por frame vem, por sua vez, do app.js do editor do three.js (MIT).
 * Alterações: nomes de mensagem do Nexus, tema atualizável por mensagem (o app manda os
 * tokens ao vivo, como já faz no sandbox livre), comentários em português. Os "stages"
 * (`mount3d` com three.js + OrbitControls + CSS2DRenderer, `mount2d` com canvas 800×450
 * letterboxed) ficam em arquivos próprios no momento da implementação; aqui só a interface.
 *
 * Empacotamento previsto: `frontend/src/ui/scene-runtime/index.ts` → Vite `build.lib`
 * (formato IIFE, global `NexusScene`) → `frontend/public/scene/runtime.js`, servido pelo
 * próprio app. A CSP do srcdoc só permite esse script e inline; nenhuma rede.
 */

import type { FromScene, SceneSetup, SceneTheme, SceneValues, ToScene } from "./scene-protocol";
import { SCENE_MSG } from "./scene-protocol";

// ───────────────────────── relógio ─────────────────────────

/** Maior passo que um frame pode avançar: aba em segundo plano ou frame lento não explode a simulação. */
export const MAX_STEP = 0.05;

/** Tempo da cena em segundos. Só anda enquanto há frames; pausar congela. */
export function createClock() {
  let time = 0;
  let last: number | null = null;
  return {
    get time() {
      return time;
    },
    /** Avança até `now` (ms do requestAnimationFrame) e devolve o passo em segundos. */
    tick(now: number): number {
      const step = last === null ? 0 : Math.min(Math.max(now - last, 0) / 1000, MAX_STEP);
      last = now;
      time += step;
      return step;
    },
    /** Esquece o último frame para o tempo não saltar depois de uma pausa. */
    hold() {
      last = null;
    },
  };
}

// ───────────────────────── reporter ─────────────────────────

/** `report()`: junta valores e manda os últimos no máximo uma vez por intervalo, só se mudaram. */
export function createReporter(send: (values: SceneValues) => void, interval = 100) {
  let latest: SceneValues = {};
  let sent = "{}";
  let timer: ReturnType<typeof setTimeout> | undefined;

  function flush() {
    timer = undefined;
    const snapshot = JSON.stringify(latest);
    if (snapshot === sent) return;
    sent = snapshot;
    send(latest);
  }

  return (values: SceneValues) => {
    latest = { ...latest, ...values };
    timer ??= setTimeout(flush, interval);
  };
}

// ───────────────────────── laço ─────────────────────────

type FrameHandler = (t: number, dt: number) => void;

/** O que um stage (2D ou 3D) entrega ao núcleo. */
export type Stage = {
  /** Globais expostos ao código do modelo (`THREE`, `scene`, `camera`, `controls`, `label` ou `ctx`). */
  globals: Record<string, unknown>;
  render(): void;
  /** 3D: adota `scene`/`camera` que o modelo criou por conta própria. */
  adopt?(scene: unknown, camera: unknown): void;
  /** Recebe o tema novo (cor de rótulos, acento). */
  retheme?(theme: SceneTheme): void;
};

export type MountStage = (
  title: string,
  theme: SceneTheme,
  fail: (message: string) => void,
) => Stage;

const handlers: FrameHandler[] = [];
const clock = createClock();
const report = createReporter((values) => send({ type: SCENE_MSG.report, values }));
let params: Record<string, unknown> = {};
let stage: Stage | undefined;
let paused = false;
let failed = false;
let scheduled = false;

/**
 * Chamado pelo srcdoc antes do código do modelo. Expõe os globais: `params`, `theme`,
 * `onFrame`, `report` e o que o stage der.
 */
export function setup(
  { title, mode, theme, params: initial, paused: startPaused }: SceneSetup,
  mount: { "3d": MountStage; "2d": MountStage },
) {
  addEventListener("error", (event) => fail(event.error ?? event.message));
  addEventListener("unhandledrejection", (event) => fail(event.reason));
  params = { ...initial };
  paused = startPaused;
  stage = mount[mode](title, theme, fail);
  const onFrame = (handler: FrameHandler) => void handlers.push(handler);
  Object.assign(globalThis, stage.globals, { params, theme, onFrame, report });
}

/** Chamado pelo srcdoc depois do código do modelo. */
export function start(ownScene: unknown, ownCamera: unknown) {
  if (failed) return;
  stage?.adopt?.(ownScene, ownCamera);
  addEventListener("message", receive);
  addEventListener("resize", () => {
    if (paused) draw(0);
  });
  send({ type: SCENE_MSG.ready });
  if (paused) draw(0);
  else schedule();
}

function receive(event: MessageEvent<ToScene>) {
  if (event.source !== parent) return;
  const message = event.data;
  if (!message || typeof message !== "object") return;
  switch (message.type) {
    case SCENE_MSG.params:
      // Mesmo objeto: o código do modelo lê `params.x` dentro do onFrame e vê o valor novo.
      Object.assign(params, message.values);
      if (paused) draw(0);
      break;
    case SCENE_MSG.pause:
      paused = true;
      clock.hold();
      break;
    case SCENE_MSG.play:
      paused = false;
      schedule();
      break;
    case SCENE_MSG.theme:
      stage?.retheme?.(message.theme);
      if (paused) draw(0);
      break;
  }
}

function schedule() {
  if (scheduled || paused || failed) return;
  scheduled = true;
  requestAnimationFrame((now) => {
    scheduled = false;
    if (paused || failed) return;
    draw(clock.tick(now));
    schedule();
  });
}

function draw(dt: number) {
  if (failed) return;
  try {
    for (const handler of handlers) handler(clock.time, dt);
    stage?.render();
  } catch (error) {
    fail(error);
  }
}

/** Primeiro erro para tudo e avisa o app; o app mostra "Reiniciar" e "Pedir correção". */
function fail(error: unknown) {
  if (failed) return;
  failed = true;
  send({
    type: SCENE_MSG.error,
    message: error instanceof Error ? error.message : String(error),
  });
}

function send(message: FromScene) {
  parent.postMessage(message, "*");
}
