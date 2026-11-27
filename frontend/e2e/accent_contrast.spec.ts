import { expect, test } from "@playwright/test";
import {
  ACCENT_PRESETS,
  DEFAULT_ACCENT,
  SURFACES,
  TEXT_CONTRAST,
  UI_CONTRAST,
  accentCssVariables,
  blend,
  contrastRatio,
  deriveAccent,
  hexToRgb,
  hslToRgb,
  normalizeHex,
  relativeLuminance,
  rgbToHex,
  rgbToHsl,
  type ColorScheme,
} from "../src/theme/accent";

// Pure colour maths: no browser is launched for these.

const SCHEMES: ColorScheme[] = ["dark", "light"];

function gridColors(): string[] {
  const colors: string[] = ["#000000", "#ffffff", "#808080", "#ffff00", "#00ffff", "#ff00ff", "#ff0000", "#00ff00", "#0000ff"];
  for (let h = 0; h < 360; h += 15) {
    for (const s of [0.15, 0.5, 0.85, 1]) {
      for (const l of [0.05, 0.15, 0.3, 0.45, 0.55, 0.7, 0.85, 0.95]) {
        colors.push(rgbToHex(hslToRgb({ h, s, l })));
      }
    }
  }
  return colors;
}

test("contrast ratio matches WCAG reference values", () => {
  expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
  expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  expect(contrastRatio("#777777", "#ffffff")).toBeCloseTo(4.48, 1);
  expect(contrastRatio("#767676", "#ffffff")).toBeGreaterThanOrEqual(4.5);
  expect(relativeLuminance("#ff0000")).toBeCloseTo(0.2126, 4);
  expect(contrastRatio("#123456", "#abcdef")).toBeCloseTo(contrastRatio("#abcdef", "#123456"), 10);
});

test("hex parsing, normalisation and colour-space round trips", () => {
  expect(normalizeHex("#ABC")).toBe("#aabbcc");
  expect(normalizeHex("2F7CF6")).toBe("#2f7cf6");
  expect(normalizeHex(" #2F7CF6 ")).toBe("#2f7cf6");
  for (const bad of ["", "#12", "#12345", "#1234567", "red", "#ggg", "#12345g"]) expect(normalizeHex(bad)).toBeNull();
  expect(hexToRgb("#bc2184")).toEqual({ r: 188, g: 33, b: 132 });
  for (const hex of ["#bc2184", "#2f7cf6", "#f2c200", "#101010"]) {
    expect(rgbToHex(hslToRgb(rgbToHsl(hexToRgb(hex))))).toBe(hex);
  }
  expect(blend("#ffffff", "#000000", 0.5)).toBe("#808080");
});

test("every colour yields readable text on fills and accent text on surfaces in both schemes", () => {
  const failures: string[] = [];
  for (const scheme of SCHEMES) {
    const surf = SURFACES[scheme];
    for (const input of gridColors()) {
      const t = deriveAccent(input, scheme);
      const onFill = contrastRatio(t.onFill, t.fill);
      if (onFill < TEXT_CONTRAST) failures.push(`${scheme} ${input}: text on fill ${onFill.toFixed(2)}`);
      const onStrong = contrastRatio(t.onFill, t.fillStrong);
      if (onStrong < TEXT_CONTRAST) failures.push(`${scheme} ${input}: text on gradient start ${onStrong.toFixed(2)}`);
      for (const surface of [surf.bg, surf.surface, surf.surface2]) {
        const fillVsSurface = contrastRatio(t.fill, surface);
        if (fillVsSurface < UI_CONTRAST) failures.push(`${scheme} ${input}: fill vs ${surface} ${fillVsSurface.toFixed(2)}`);
      }
      for (const surface of [surf.bg, surf.surface, surf.surface2, surf.surface3, blend(t.fill, surf.surface2, 0.22), blend(t.fill, surf.surface3, 0.22)]) {
        const textVsSurface = contrastRatio(t.text, surface);
        if (textVsSurface < TEXT_CONTRAST) failures.push(`${scheme} ${input}: accent text vs ${surface} ${textVsSurface.toFixed(2)}`);
      }
    }
  }
  expect(failures.slice(0, 10)).toEqual([]);
});

test("every preset is readable and the ERA preset is the brand default", () => {
  expect(ACCENT_PRESETS[0].hex).toBe(DEFAULT_ACCENT);
  expect(new Set(ACCENT_PRESETS.map((p) => p.hex)).size).toBe(ACCENT_PRESETS.length);
  for (const preset of ACCENT_PRESETS) {
    for (const scheme of SCHEMES) {
      const t = deriveAccent(preset.hex, scheme);
      expect(contrastRatio(t.onFill, t.fill), `${preset.id}/${scheme} on-fill`).toBeGreaterThanOrEqual(TEXT_CONTRAST);
      expect(contrastRatio(t.text, SURFACES[scheme].surface), `${preset.id}/${scheme} text`).toBeGreaterThanOrEqual(TEXT_CONTRAST);
    }
  }
});

test("a mid-lightness colour in the white/dark dead zone is nudged until legible", () => {
  // Luminance ~0.19 fails both white and dark text; the helper must move out of that band.
  const t = deriveAccent("#b0722a", "dark");
  expect(contrastRatio(t.onFill, t.fill)).toBeGreaterThanOrEqual(TEXT_CONTRAST);
});

test("derivation keeps the hue of the chosen colour where it can and is idempotent", () => {
  const blue = deriveAccent("#2f7cf6", "dark");
  const hueOf = (hex: string) => rgbToHsl(hexToRgb(hex)).h;
  expect(Math.abs(hueOf(blue.fill) - hueOf("#2f7cf6"))).toBeLessThan(6);
  expect(Math.abs(hueOf(blue.text) - hueOf("#2f7cf6"))).toBeLessThan(6);
  const again = deriveAccent(blue.fill, "dark");
  expect(again.fill).toBe(blue.fill);
});

test("invalid input falls back to the ERA colour and exports a complete token set", () => {
  const fallback = deriveAccent("not-a-colour");
  expect(fallback.fill).toBe(deriveAccent(DEFAULT_ACCENT).fill);
  const vars = accentCssVariables(deriveAccent("#2f7cf6"));
  for (const key of [
    "--era-primary", "--era-primary-strong", "--era-on-primary", "--era-cyan", "--era-focus", "--era-selected",
    "--era-accent-rgb", "--era-accent-text-rgb", "--era-accent-deep-rgb", "--era-accent-deep",
  ]) {
    expect(vars[key], key).toBeTruthy();
  }
  expect(vars["--era-accent-rgb"]).toMatch(/^\d{1,3}, \d{1,3}, \d{1,3}$/);
});
