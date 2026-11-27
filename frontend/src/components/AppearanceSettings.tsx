import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  ACCENT_PRESETS,
  DEFAULT_ACCENT,
  accentCssVariables,
  deriveAccent,
  normalizeHex,
} from "../theme/accent";
import { persistAccent, saveAccent, setAccentLocal, useAccent } from "../theme/accentStore";
import { useMotionPreference } from "../motion/MotionPreference";
import { Card } from "./Card";

type SaveState = "idle" | "saving" | "saved" | "offline";

const SAVE_DEBOUNCE_MS = 500;

const swatchBase: CSSProperties = {
  width: 44,
  height: 44,
  minHeight: 44,
  padding: 0,
  borderRadius: "50%",
  flex: "0 0 auto",
};

export function AppearanceSettings() {
  const accent = useAccent();
  const motion = useMotionPreference();
  const [draft, setDraft] = useState(accent ?? DEFAULT_ACCENT);
  const [hexText, setHexText] = useState((accent ?? DEFAULT_ACCENT).toUpperCase());
  const [hexError, setHexError] = useState(false);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  useEffect(() => {
    const external = accent ?? DEFAULT_ACCENT;
    if (external.toLowerCase() !== draft.toLowerCase() && (accent !== null || !hexError)) {
      setDraft(external);
      setHexText(external.toUpperCase());
    }
    // Only follow external changes (e.g. cross-device sync), not our own typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accent]);

  const effective = accent ?? DEFAULT_ACCENT;
  const preview = useMemo(() => deriveAccent(draft, "dark"), [draft]);
  const previewVars = useMemo(() => accentCssVariables(preview) as CSSProperties, [preview]);
  const adjusted = preview.fill.toLowerCase() !== draft.toLowerCase();
  const isDefault = accent === null;

  const finishSave = async (promise: Promise<boolean>) => {
    setSaveState("saving");
    setSaveState((await promise) ? "saved" : "offline");
  };

  const choose = (hex: string, options: { debounce: boolean }) => {
    const normalized = normalizeHex(hex);
    if (!normalized) return;
    setDraft(normalized);
    setHexText(normalized.toUpperCase());
    setHexError(false);
    if (timer.current !== null) window.clearTimeout(timer.current);
    if (normalized === DEFAULT_ACCENT) {
      void finishSave(saveAccent(null));
      return;
    }
    if (!options.debounce) {
      void finishSave(saveAccent(normalized));
      return;
    }
    setAccentLocal(normalized);
    setSaveState("saving");
    timer.current = window.setTimeout(() => void finishSave(persistAccent()), SAVE_DEBOUNCE_MS);
  };

  const onHexInput = (value: string) => {
    setHexText(value);
    const trimmed = value.trim();
    if (/^#?[0-9a-f]{6}$/i.test(trimmed)) {
      const normalized = normalizeHex(trimmed);
      if (normalized) choose(normalized, { debounce: true });
      return;
    }
    setHexError(trimmed.length >= 7 && normalizeHex(trimmed) === null);
  };

  const onHexBlur = () => {
    const trimmed = hexText.trim();
    if (trimmed.length === 0) return;
    const normalized = normalizeHex(trimmed);
    if (!normalized) {
      setHexError(true);
      return;
    }
    choose(normalized, { debounce: false });
  };

  const reset = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    setDraft(DEFAULT_ACCENT);
    setHexText(DEFAULT_ACCENT.toUpperCase());
    setHexError(false);
    void finishSave(saveAccent(null));
  };

  return (
    <Card>
      <section aria-labelledby="appearance-title" style={{ display: "flex", flexDirection: "column", gap: "0.9rem", minWidth: 0 }}>
        <div>
          <h2 id="appearance-title" style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Оформление</h2>
          <p style={{ margin: "0.3rem 0 0", color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>
            Выбери свой цвет. Он применяется сразу и сохраняется на всех твоих устройствах.
          </p>
        </div>

        <div role="group" aria-label="Готовые цвета" style={{ display: "flex", flexWrap: "wrap", gap: "0.55rem" }}>
          {ACCENT_PRESETS.map((preset) => {
            const selected = effective.toLowerCase() === preset.hex.toLowerCase();
            return (
              <button
                key={preset.id}
                type="button"
                aria-label={preset.name}
                aria-pressed={selected}
                title={preset.name}
                onClick={() => choose(preset.hex, { debounce: false })}
                style={{
                  ...swatchBase,
                  background: preset.hex,
                  border: selected ? "3px solid var(--era-text)" : "2px solid var(--era-border-strong)",
                  boxShadow: selected ? "0 0 0 2px var(--era-bg)" : "none",
                }}
              />
            );
          })}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", gap: "0.6rem", alignItems: "center" }}>
          <label style={{ display: "contents" }}>
            <span className="era-sr-only">Свой цвет</span>
            <input
              type="color"
              aria-label="Свой цвет"
              value={draft}
              onChange={(event) => choose(event.target.value, { debounce: true })}
              style={{ width: 56, minWidth: 56, height: 44, padding: 2, cursor: "pointer" }}
            />
          </label>
          <label style={{ display: "flex", flexDirection: "column", gap: "0.2rem", minWidth: 0 }}>
            <span style={{ fontSize: "var(--era-text-xs)", color: "var(--era-text-secondary)" }}>Код цвета</span>
            <input
              inputMode="text"
              autoCapitalize="characters"
              autoCorrect="off"
              spellCheck={false}
              maxLength={7}
              value={hexText}
              aria-invalid={hexError}
              aria-describedby={hexError ? "appearance-hex-error" : undefined}
              onChange={(event) => onHexInput(event.target.value)}
              onBlur={onHexBlur}
              onKeyDown={(event) => {
                if (event.key === "Enter") onHexBlur();
              }}
              placeholder="#BC2184"
            />
          </label>
        </div>
        {hexError && (
          <p id="appearance-hex-error" role="alert" style={{ margin: 0, color: "var(--era-error)", fontSize: "var(--era-text-sm)" }}>
            Введи цвет в формате #RRGGBB, например #2F7CF6.
          </p>
        )}

        <div
          data-testid="appearance-preview"
          aria-label="Предпросмотр"
          role="group"
          style={{
            ...previewVars,
            display: "flex",
            flexDirection: "column",
            gap: "0.6rem",
            padding: "0.85rem",
            borderRadius: "var(--era-radius-md)",
            background: "var(--era-surface-2)",
            border: "1px solid var(--era-border)",
            minWidth: 0,
          }}
        >
          <span style={{ fontSize: "var(--era-text-xs)", color: "var(--era-text-secondary)" }}>Предпросмотр</span>
          <button type="button" className="era-btn-primary" tabIndex={-1} style={{ width: "100%" }}>Записаться</button>
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
            <span style={{ padding: "0.35rem 0.7rem", borderRadius: 999, background: "var(--era-selected)", color: "var(--era-cyan)", fontWeight: 800, fontSize: "0.8rem" }}>Выбрано</span>
            <span style={{ padding: "0.35rem 0.7rem", borderRadius: 999, background: "var(--era-surface)", color: "var(--era-text-secondary)", fontWeight: 700, fontSize: "0.8rem" }}>Обычная</span>
            <span style={{ padding: "0.35rem 0.7rem", borderRadius: 999, background: "var(--era-success-bg)", color: "var(--era-success)", fontWeight: 700, fontSize: "0.8rem" }}>Подтверждено</span>
          </div>
          <span style={{ color: "var(--era-cyan)", fontWeight: 800 }}>Ссылка и акценты →</span>
        </div>

        {adjusted && (
          <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>
            Оттенок немного скорректирован, чтобы текст и кнопки оставались читаемыми.
          </p>
        )}

        <button type="button" onClick={reset} disabled={isDefault} style={{ width: "100%" }}>
          Вернуть цвет ЭРА
        </button>
        <p role="status" aria-live="polite" data-testid="appearance-save-status" style={{ margin: 0, minHeight: "1.2em", color: "var(--era-text-secondary)", fontSize: "var(--era-text-sm)" }}>
          {saveState === "saving" && "Сохраняем…"}
          {saveState === "saved" && "Цвет сохранён на всех устройствах"}
          {saveState === "offline" && "Цвет применён здесь, на других устройствах появится при следующем подключении"}
        </p>

        <button type="button" aria-pressed={motion.liveBackground} onClick={motion.toggleLiveBackground} style={{ width: "100%", textAlign: "left" }}>
          Живой фон · {motion.liveBackground ? "Включён" : "Выключен"}
        </button>
      </section>
    </Card>
  );
}
