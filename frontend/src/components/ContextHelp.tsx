import { useEffect, useMemo, useState } from "react";
import { resolveHelpTopic, type HelpContent, type HelpMode } from "../help/helpContentRegistry";
import { BottomSheet } from "./BottomSheet";

export type ContextHelpMode = HelpMode;

function currentRoute(): string {
  const params = new URLSearchParams(window.location.search);
  const queryRoute = params.get("eraPath") || params.get("tgWebAppStartParam");
  if (queryRoute) {
    if (queryRoute.startsWith("event_")) return `events/${queryRoute.slice(6)}`;
    if (queryRoute.startsWith("project_")) return `projects/${queryRoute.slice(8)}`;
    if (queryRoute.startsWith("task_")) return `tasks/${queryRoute.slice(5)}`;
    return queryRoute.replace(/^\/?/, "").replace(/\/$/, "");
  }
  return window.location.hash.replace(/^#\/?/, "").replace(/\/$/, "") || "home";
}

function seenKey(topic: HelpContent): string {
  return `era_context_help_seen:${topic.key}:v2`;
}

function wasSeen(topic: HelpContent): boolean {
  try {
    return window.localStorage.getItem(seenKey(topic)) === "1";
  } catch {
    return false;
  }
}

function markSeen(topic: HelpContent): void {
  try {
    window.localStorage.setItem(seenKey(topic), "1");
  } catch {
    // Embedded/private clients may block storage. Help still remains usable.
  }
}

function navigate(route: string): void {
  const normalized = route.replace(/^#?\/?/, "").replace(/\/$/, "");
  window.location.hash = `#/${normalized}`;
}

interface ContextHelpProps {
  mode: ContextHelpMode;
  /** Explicit topic is useful for modal/nested screens that do not own a route. */
  topic?: string;
}

export function ContextHelp({ mode, topic: explicitTopic }: ContextHelpProps) {
  const [route, setRoute] = useState(() => currentRoute());
  const [open, setOpen] = useState(false);
  const topic = useMemo(
    () => resolveHelpTopic(mode, route, explicitTopic),
    [mode, route, explicitTopic],
  );
  const [showCoach, setShowCoach] = useState(() => !wasSeen(topic));

  useEffect(() => {
    const sync = () => setRoute(currentRoute());
    window.addEventListener("hashchange", sync);
    window.addEventListener("popstate", sync);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.removeEventListener("popstate", sync);
    };
  }, []);

  useEffect(() => {
    setOpen(false);
    setShowCoach(!wasSeen(topic));
  }, [topic]);

  const openHelp = () => {
    markSeen(topic);
    setShowCoach(false);
    setOpen(true);
    window.dispatchEvent(new CustomEvent("era:analytics", {
      detail: { event: "context_help_opened", topic: topic.key },
    }));
  };

  const runAction = () => {
    if (!topic.action) return;
    window.dispatchEvent(new CustomEvent("era:analytics", {
      detail: { event: "context_help_action_clicked", topic: topic.key },
    }));
    setOpen(false);
    navigate(topic.action.route);
  };

  const bottom = mode === "leader"
    ? "calc(1rem + env(safe-area-inset-bottom, 0px))"
    : "calc(5.5rem + env(safe-area-inset-bottom, 0px))";

  return (
    <>
      <div style={{ position: "fixed", right: "0.75rem", bottom, zIndex: 35, display: "flex", alignItems: "center", gap: "0.5rem", pointerEvents: "none" }}>
        {showCoach && (
          <button
            type="button"
            onClick={openHelp}
            style={{
              pointerEvents: "auto",
              borderRadius: "999px",
              padding: "0.52rem 0.72rem",
              border: "1px solid var(--era-border)",
              background: "color-mix(in srgb, var(--era-surface) 92%, transparent)",
              color: "var(--era-text)",
              boxShadow: "var(--era-shadow-card)",
              backdropFilter: "blur(16px)",
              fontSize: "var(--era-text-xs)",
              fontWeight: 800,
              whiteSpace: "nowrap",
            }}
          >
            Что здесь?
          </button>
        )}
        <button
          type="button"
          onClick={openHelp}
          aria-label={`Справка: ${topic.title}`}
          style={{
            pointerEvents: "auto",
            width: 42,
            height: 42,
            borderRadius: "50%",
            padding: 0,
            border: "1px solid color-mix(in srgb, var(--era-violet) 42%, var(--era-border))",
            background: "color-mix(in srgb, var(--era-surface) 92%, transparent)",
            color: "var(--era-text)",
            boxShadow: "var(--era-shadow-card)",
            backdropFilter: "blur(16px)",
            display: "grid",
            placeItems: "center",
            fontFamily: "var(--era-font-display)",
            fontSize: "1rem",
            fontWeight: 900,
          }}
        >
          i
        </button>
      </div>

      <BottomSheet open={open} onClose={() => setOpen(false)} title={topic.title}>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem", paddingBottom: "0.5rem" }}>
          <section>
            <strong style={{ display: "block", marginBottom: "0.3rem" }}>О разделе</strong>
            <p style={{ margin: 0, color: "var(--era-text-muted)", lineHeight: 1.55 }}>{topic.about}</p>
          </section>

          <section style={{ padding: "0.85rem", borderRadius: "var(--era-radius-card)", background: "var(--era-surface-2)", border: "1px solid var(--era-border)" }}>
            <strong style={{ display: "block", marginBottom: "0.5rem" }}>Что здесь можно сделать</strong>
            <ul style={{ margin: 0, paddingLeft: "1.15rem", color: "var(--era-text-muted)", display: "grid", gap: "0.35rem", lineHeight: 1.45 }}>
              {topic.actions.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section style={{ padding: "0.85rem", borderRadius: "var(--era-radius-card)", background: "var(--era-surface-2)", border: "1px solid var(--era-border)" }}>
            <strong style={{ display: "block", marginBottom: "0.5rem" }}>Как это работает</strong>
            <ol style={{ margin: 0, paddingLeft: "1.15rem", color: "var(--era-text-muted)", display: "grid", gap: "0.35rem", lineHeight: 1.45 }}>
              {topic.steps.map((item) => <li key={item}>{item}</li>)}
            </ol>
          </section>

          <section style={{ padding: "0.85rem", borderRadius: "var(--era-radius-card)", background: "var(--era-tint-violet, var(--era-surface-2))", border: "1px solid color-mix(in srgb, var(--era-violet) 22%, var(--era-border))" }}>
            <strong style={{ display: "block", marginBottom: "0.3rem" }}>Совет</strong>
            <p style={{ margin: 0, lineHeight: 1.5 }}>{topic.tip}</p>
          </section>

          {topic.action && (
            <button type="button" className="era-btn-primary" onClick={runAction} style={{ width: "100%" }}>
              {topic.action.label}
            </button>
          )}
        </div>
      </BottomSheet>
    </>
  );
}
