/**
 * Personal accent colour: pure colour maths plus the derivation of every
 * accent-dependent design token. No DOM access here so it can be unit tested.
 *
 * The user picks one hex colour; we never apply it raw. Fills, accent text and
 * tinted backgrounds are each adjusted until they satisfy WCAG contrast against
 * the surfaces they actually sit on, in both the dark (AURA) and a light scheme.
 */

export type ColorScheme = "dark" | "light";

export interface Rgb { r: number; g: number; b: number }
export interface Hsl { h: number; s: number; l: number }

export const DEFAULT_ACCENT = "#bc2184";
export const TEXT_CONTRAST = 4.5;
export const UI_CONTRAST = 3;

const HEX_RE = /^#[0-9a-f]{6}$/i;

export interface AccentPreset { id: string; name: string; hex: string }

export const ACCENT_PRESETS: readonly AccentPreset[] = [
  { id: "era", name: "ЭРА", hex: DEFAULT_ACCENT },
  { id: "violet", name: "Фиолетовый", hex: "#7c4dff" },
  { id: "blue", name: "Синий", hex: "#2f7cf6" },
  { id: "cyan", name: "Бирюзовый", hex: "#12a5b4" },
  { id: "green", name: "Зелёный", hex: "#2fa866" },
  { id: "lime", name: "Салатовый", hex: "#9acd32" },
  { id: "yellow", name: "Жёлтый", hex: "#f2c200" },
  { id: "orange", name: "Оранжевый", hex: "#f2711c" },
  { id: "red", name: "Красный", hex: "#e53935" },
  { id: "graphite", name: "Графит", hex: "#8b94a7" },
];

/** Surfaces the accent must stay legible on. `ink` is the dark text colour. */
export const SURFACES: Record<ColorScheme, { bg: string; surface: string; surface2: string; surface3: string; ink: string }> = {
  dark: { bg: "#19091a", surface: "#321731", surface2: "#432040", surface3: "#542651", ink: "#19091a" },
  light: { bg: "#fbf4fa", surface: "#ffffff", surface2: "#f6e9f4", surface3: "#ecd7e8", ink: "#19091a" },
};

const WHITE = "#ffffff";

export function isValidHex(value: unknown): value is string {
  return typeof value === "string" && HEX_RE.test(value);
}

export function normalizeHex(value: string): string | null {
  const trimmed = value.trim();
  const withHash = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  if (/^#[0-9a-f]{3}$/i.test(withHash)) {
    const [, a, b, c] = withHash;
    return `#${a}${a}${b}${b}${c}${c}`.toLowerCase();
  }
  return isValidHex(withHash) ? withHash.toLowerCase() : null;
}

export function hexToRgb(hex: string): Rgb {
  const n = parseInt(hex.slice(1), 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

export function rgbToHex({ r, g, b }: Rgb): string {
  const part = (v: number) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

export function rgbToHsl({ r, g, b }: Rgb): Hsl {
  const rn = r / 255, gn = g / 255, bn = b / 255;
  const max = Math.max(rn, gn, bn), min = Math.min(rn, gn, bn);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === rn) h = ((gn - bn) / d) % 6;
  else if (max === gn) h = (bn - rn) / d + 2;
  else h = (rn - gn) / d + 4;
  return { h: (h * 60 + 360) % 360, s, l };
}

export function hslToRgb({ h, s, l }: Hsl): Rgb {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const [r, g, b] =
    h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return { r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 };
}

function channel(v: number): number {
  const s = v / 255;
  return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
}

export function relativeLuminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.x contrast ratio, 1..21. */
export function contrastRatio(a: string, b: string): number {
  const la = relativeLuminance(a), lb = relativeLuminance(b);
  const hi = Math.max(la, lb), lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

/** Composite `fg` at `alpha` over opaque `bg`. */
export function blend(fg: string, bg: string, alpha: number): string {
  const f = hexToRgb(fg), b = hexToRgb(bg);
  return rgbToHex({ r: f.r * alpha + b.r * (1 - alpha), g: f.g * alpha + b.g * (1 - alpha), b: f.b * alpha + b.b * (1 - alpha) });
}

function withLightness(hsl: Hsl, l: number): string {
  return rgbToHex(hslToRgb({ ...hsl, l: Math.max(0, Math.min(1, l)) }));
}

/** Step lightness in `direction` until `ok(hex)`; returns the last candidate if never satisfied. */
function stepUntil(hsl: Hsl, direction: 1 | -1, ok: (hex: string) => boolean): string {
  let l = hsl.l;
  let hex = withLightness(hsl, l);
  for (let i = 0; i < 100 && !ok(hex); i += 1) {
    l += direction * 0.01;
    if (l < 0 || l > 1) break;
    hex = withLightness(hsl, l);
  }
  return hex;
}

export function bestOnColor(fill: string, ink: string): { color: string; ratio: number } {
  const white = contrastRatio(fill, WHITE);
  const dark = contrastRatio(fill, ink);
  // Prefer white (brand default) whenever it is itself legible.
  if (white >= TEXT_CONTRAST || white >= dark) return { color: WHITE, ratio: white };
  return { color: ink, ratio: dark };
}

export interface AccentTokens {
  /** Solid fill for buttons, active tabs, avatars. */
  fill: string;
  /** Gradient start / pressed state; keeps the same on-colour contrast as `fill`. */
  fillStrong: string;
  /** Darkest gradient stop (decorative; never carries text). */
  fillDeep: string;
  /** Text colour that is legible on `fill` and `fillStrong`. */
  onFill: string;
  /** Accent-coloured text/icons on page surfaces (links, selected tab labels). */
  text: string;
  /** Text legible on top of `text` used as a background. */
  onText: string;
  scheme: ColorScheme;
}

export function deriveAccent(input: string, scheme: ColorScheme = "dark"): AccentTokens {
  const base = isValidHex(input) ? input.toLowerCase() : DEFAULT_ACCENT;
  const hsl = rgbToHsl(hexToRgb(base));
  const surf = SURFACES[scheme];
  // Lighten on dark UI, darken on light UI: the direction that increases separation.
  const away: 1 | -1 = scheme === "dark" ? 1 : -1;
  const surfaces = [surf.bg, surf.surface, surf.surface2];

  const fillVisible = (hex: string) => surfaces.every((s) => contrastRatio(hex, s) >= UI_CONTRAST);
  let fill = stepUntil(hsl, away, fillVisible);

  // The luminance band ~0.18..0.20 fails for both white and dark text; nudge out of it.
  const fillReadable = (hex: string) => bestOnColor(hex, surf.ink).ratio >= TEXT_CONTRAST;
  if (!fillReadable(fill)) fill = stepUntil(rgbToHsl(hexToRgb(fill)), away, fillReadable);

  const on = bestOnColor(fill, surf.ink);
  const fillHsl = rgbToHsl(hexToRgb(fill));
  // Move toward the side that increases contrast with the on-colour.
  const towardContrast: 1 | -1 = on.color === WHITE ? -1 : 1;
  const strong = withLightness(fillHsl, fillHsl.l + towardContrast * 0.08);
  const deep = withLightness(fillHsl, fillHsl.l * 0.55);

  const selectedBg = (s: string) => blend(fill, s, 0.22);
  const textBackdrops = [...surfaces, surf.surface3, selectedBg(surf.surface2), selectedBg(surf.surface3)];
  const textOk = (hex: string) => textBackdrops.every((s) => contrastRatio(hex, s) >= TEXT_CONTRAST);
  const text = stepUntil(rgbToHsl(hexToRgb(base)), away, textOk);

  return {
    fill,
    fillStrong: contrastRatio(strong, on.color) >= contrastRatio(fill, on.color) ? strong : fill,
    fillDeep: deep,
    onFill: on.color,
    text,
    onText: bestOnColor(text, surf.ink).color,
    scheme,
  };
}

function rgbTriplet(hex: string): string {
  const { r, g, b } = hexToRgb(hex);
  return `${r}, ${g}, ${b}`;
}

/** CSS custom properties to set on :root for a derived accent. */
export function accentCssVariables(tokens: AccentTokens): Record<string, string> {
  return {
    "--era-primary": tokens.fill,
    "--era-primary-strong": tokens.fillStrong,
    "--era-on-primary": tokens.onFill,
    "--era-cyan": tokens.text,
    "--era-on-cyan": tokens.onText,
    "--era-focus": tokens.text,
    // Legacy aliases are mostly used as *text/outline* colours, so they take the
    // text-grade colour. Solid fills use --era-primary explicitly.
    "--era-blue": tokens.text,
    "--era-violet": tokens.text,
    "--era-red": tokens.text,
    "--era-deep-red": tokens.text,
    "--era-accent-deep": tokens.fillDeep,
    "--era-accent-rgb": rgbTriplet(tokens.fill),
    "--era-accent-text-rgb": rgbTriplet(tokens.text),
    "--era-accent-deep-rgb": rgbTriplet(tokens.fillStrong),
    "--era-selected": `rgba(${rgbTriplet(tokens.fill)}, 0.22)`,
  };
}
