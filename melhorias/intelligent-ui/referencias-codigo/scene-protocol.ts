/**
 * Protocolo app ↔ cena (iframe) para o bloco `sandbox` com `kind: "scene"` (plano 13).
 *
 * Adaptado de AnswerUI — https://github.com/0xcro3dile/answerui (src/scene/protocol.ts)
 * MIT License, Copyright (c) 2026 0xcro3dile. Alterações: nomes de mensagem com prefixo
 * `__nexus_scene_` (para não colidir com `__nexus_ogui_resize`/`nexus_action` do sandbox
 * livre), tokens de tema no formato do themeBridge do Multi+ e comentários em português.
 *
 * Regra de ouro: o iframe roda código escrito pelo modelo. Tudo que chega dele passa por
 * `readSceneMessage`, que só aceita três tipos e corta tamanhos. O que não bater é ignorado.
 */

export type SceneMode = "3d" | "2d";

/** Tema que a cena recebe no `setup` e por mensagem quando o usuário troca o tema do app. */
export type SceneTheme = {
  dark: boolean;
  /** Cor de texto para rótulos (`label()`), vinda de `--ink`. */
  text: string;
  /** Cor de destaque, vinda de `--primary`. */
  accent: string;
};

export type SceneValue = number | string | boolean;
export type SceneValues = Record<string, SceneValue>;

/** Dados embutidos no srcdoc: a cena começa com eles antes de qualquer mensagem. */
export type SceneSetup = {
  title: string;
  mode: SceneMode;
  theme: SceneTheme;
  /** Valores iniciais dos controles ligados à cena (`params` dentro do código). */
  params: Record<string, unknown>;
  /** `true` quando `prefers-reduced-motion` está ativo: a cena desenha um frame e espera. */
  paused: boolean;
};

export const SCENE_MSG = {
  params: "__nexus_scene_params",
  pause: "__nexus_scene_pause",
  play: "__nexus_scene_play",
  theme: "__nexus_scene_theme",
  ready: "__nexus_scene_ready",
  report: "__nexus_scene_report",
  error: "__nexus_scene_error",
} as const;

/** App → cena. */
export type ToScene =
  | { type: typeof SCENE_MSG.params; values: Record<string, unknown> }
  | { type: typeof SCENE_MSG.pause }
  | { type: typeof SCENE_MSG.play }
  | { type: typeof SCENE_MSG.theme; theme: SceneTheme };

/** Cena → app. */
export type FromScene =
  | { type: typeof SCENE_MSG.ready }
  | { type: typeof SCENE_MSG.report; values: SceneValues }
  | { type: typeof SCENE_MSG.error; message: string };

/** Tetos do que a cena pode mandar de volta (spec §4.5, extensão `scene`). */
export const MAX_REPORT_KEYS = 20;
export const MAX_REPORT_TEXT = 200;
export const MAX_ERROR_TEXT = 500;

/**
 * Lê uma mensagem vinda do iframe. Devolve `null` para qualquer coisa fora do protocolo.
 * O chamador ainda precisa conferir `event.source === iframe.contentWindow`.
 */
export function readSceneMessage(data: unknown): FromScene | null {
  if (!isRecord(data)) return null;
  switch (data.type) {
    case SCENE_MSG.ready:
      return { type: SCENE_MSG.ready };
    case SCENE_MSG.error:
      return { type: SCENE_MSG.error, message: String(data.message).slice(0, MAX_ERROR_TEXT) };
    case SCENE_MSG.report:
      return isRecord(data.values)
        ? { type: SCENE_MSG.report, values: readValues(data.values) }
        : null;
    default:
      return null;
  }
}

function readValues(values: Record<string, unknown>): SceneValues {
  const valid = Object.entries(values).filter(([, value]) => isSceneValue(value));
  return Object.fromEntries(valid.slice(0, MAX_REPORT_KEYS)) as SceneValues;
}

function isSceneValue(value: unknown): value is SceneValue {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string") return value.length <= MAX_REPORT_TEXT;
  return typeof value === "boolean";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
