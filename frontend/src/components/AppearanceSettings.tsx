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
  width: 34,
  height: 34,
  minWidth: 34,
  minHeight: 34,
  padding: 0,
  borderRadius: "50%",
  flex: "0 0 auto",
};

export function AppearanceSettings() {
  const accent = useAccent();
  const motion = useMotionPreference();
  const [expanded, setExpanded] = useState(false);
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
  const currentPreset = useMemo(
    () => ACCENT_PRESETS.find((preset) => preset.hex.toLowerCase() === effective.toLowerCase()) ?? null,
    [effective],
  );
  const currentLabel = currentPreset ? currentPreset.name : effective.toUpperCase();
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
    <Card style={{ padding: "0.65rem 0.85rem" }}>
      <section
        aria-labelledby="appearance-title"
        data-testid="appearance-settings"
        style={{ display: "flex", flexDirection: "column", gap: expanded ? "0.6rem" : 0, minWidth: 0 }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.55rem",
            flexWrap: "wrap",
            minWidth: 0,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.55rem", minWidth: 0, flex: "1 1 8rem" }}>
            <span
              aria-hidden="true"
              data-testid="appearance-current-swatch"
              style={{
                width: 24,
                height: 24,
                borderRadius: "50%",
                background: effective,
                border: "2px solid var(--era-border-strong)",
                flexShrink: 0,
              }}
            />
            <div style={{ minWidth: 0, display: "flex", flexDirection: "column", gap: "0.05rem" }}>
              <h2 id="appearance-title" style={{ margin: 0, fontSize: "var(--era-text-base)", lineHeight: 1.2 }}>
                Оформление
              </h2>
              <span
                data-testid="appearance-summary"
                style={{
                  fontSize: "var(--era-text-xs)",
                  color: "var(--era-text-secondary)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {currentLabel}
              </span>
            </div>
          </div>
          <button
            type="button"
            aria-expanded={expanded}
            aria-controls="appearance-panel"
            onClick={() => setExpanded((prev) => !prev)}
            style={{
              minHeight: 36,
              padding: "0.3rem 0.7rem",
              fontSize: "var(--era-text-sm)",
              borderRadius: "var(--era-radius-pill)",
              background: expanded ? "var(--era-surface-2)" : "var(--era-selected)",
              color: expanded ? "var(--era-text)" : "var(--era-cyan)",
              border: "1px solid var(--era-border)",
              flexShrink: 0,
            }}
          >
            {expanded ? "Свернуть" : "Изменить"}
          </button>
        </div>

        {expanded && (
          <div id="appearance-panel" style={{ display: "flex", flexDirection: "column", gap: "0.55rem", minWidth: 0 }}>
            <div
              role="group"
              aria-label="Готовые цвета"
              className="era-pilltabs-scroller"
              style={{
                display: "flex",
                flexWrap: "nowrap",
                gap: "0.45rem",
                overflowX: "auto",
                padding: "4px 3px",
                margin: "0 -3px",
                minWidth: 0,
              }}
            >
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
                      border: selected ? "2.5px solid var(--era-text)" : "1.5px solid var(--era-border-strong)",
                      boxShadow: selected ? "0 0 0 2px var(--era-bg)" : "none",
                    }}
                  />
                );
              })}
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap", minWidth: 0 }}>
              <label style={{ display: "contents" }}>
                <span className="era-sr-only">Свой цвет</span>
                <input
                  type="color"
                  aria-label="Свой цвет"
                  value={draft}
                  onChange={(event) => choose(event.target.value, { debounce: true })}
                  style={{ width: 38, minWidth: 38, height: 38, minHeight: 38, padding: 2, cursor: "pointer", flex: "0 0 auto" }}
                />
              </label>
              <label style={{ display: "flex", flex: "1 1 5.5rem", minWidth: 0 }}>
                <span className="era-sr-only">Код цвета</span>
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
                  style={{ minHeight: 38, height: 38, padding: "0.35rem 0.6rem", fontSize: "var(--era-text-sm)", minWidth: 0 }}
                />
              </label>
              <button
                type="button"
                onClick={reset}
                disabled={isDefault}
                aria-label="Вернуть цвет ЭРА"
                title="Вернуть цвет ЭРА"
                style={{
                  minHeight: 38,
                  padding: "0.35rem 0.65rem",
                  fontSize: "var(--era-text-sm)",
                  flexShrink: 0,
                }}
              >
                Сброс
              </button>
            </div>

            {hexError && (
              <p id="appearance-hex-error" role="alert" style={{ margin: 0, color: "var(--era-error)", fontSize: "var(--era-text-xs)" }}>
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
                alignItems: "center",
                gap: "0.45rem",
                flexWrap: "wrap",
                padding: "0.45rem 0.55rem",
                borderRadius: "var(--era-radius-sm)",
                background: "var(--era-surface-2)",
                border: "1px solid var(--era-border)",
                minWidth: 0,
              }}
            >
              <button
                type="button"
                className="era-btn-primary"
                tabIndex={-1}
                style={{ minHeight: 32, padding: "0.25rem 0.7rem", fontSize: "var(--era-text-xs)" }}
              >
                Кнопка
              </button>
              <span
                style={{
                  padding: "0.22rem 0.55rem",
                  borderRadius: 999,
                  background: "var(--era-selected)",
                  color: "var(--era-cyan)",
                  fontWeight: 800,
                  fontSize: "var(--era-text-xs)",
                }}
              >
                Выбрано
              </span>
              <span style={{ color: "var(--era-cyan)", fontWeight: 700, fontSize: "var(--era-text-xs)", marginLeft: "auto" }}>
                Акцент →
              </span>
            </div>

            {adjusted && (
              <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "var(--era-text-xs)" }}>
                Оттенок немного скорректирован для читаемости.
              </p>
            )}

            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "0.5rem",
                minWidth: 0,
              }}
            >
              <span id="appearance-live-bg-label" style={{ fontSize: "var(--era-text-sm)", color: "var(--era-text-secondary)" }}>
                Живой фон
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={motion.liveBackground}
                aria-labelledby="appearance-live-bg-label"
                onClick={motion.toggleLiveBackground}
                style={{
                  minHeight: 32,
                  minWidth: 54,
                  padding: "0.2rem 0.6rem",
                  borderRadius: "var(--era-radius-pill)",
                  fontSize: "var(--era-text-xs)",
                  fontWeight: 700,
                  background: motion.liveBackground ? "var(--era-selected)" : "var(--era-surface-2)",
                  border: motion.liveBackground ? "1px solid var(--era-border-strong)" : "1px solid var(--era-border)",
                  color: motion.liveBackground ? "var(--era-cyan)" : "var(--era-text-secondary)",
                  flexShrink: 0,
                }}
              >
                {motion.liveBackground ? "Вкл" : "Выкл"}
              </button>
            </div>

            <p
              role="status"
              aria-live="polite"
              data-testid="appearance-save-status"
              style={{
                margin: 0,
                color: "var(--era-text-secondary)",
                fontSize: "var(--era-text-xs)",
                display: saveState === "idle" ? "none" : "block",
              }}
            >
              {saveState === "saving" && "Сохраняем…"}
              {saveState === "saved" && "Цвет сохранён на всех устройствах"}
              {saveState === "offline" && "Цвет применён здесь, на других устройствах появится при следующем подключении"}
            </p>
          </div>
        )}
      </section>
    </Card>
  );
}
