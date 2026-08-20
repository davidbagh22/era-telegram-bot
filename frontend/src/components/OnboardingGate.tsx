import { useEffect, useState, type ReactNode } from "react";
import {
  completeParticipationOnboarding,
  fetchParticipation,
  type ParticipationState,
} from "../api/participation";
import { Card } from "./Card";
import { MonoLabel } from "./MonoLabel";
import { SkeletonCard } from "./Skeleton";

interface OnboardingGateProps {
  children: ReactNode;
}

export function OnboardingGate({ children }: OnboardingGateProps) {
  const [state, setState] = useState<ParticipationState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let mounted = true;
    void fetchParticipation()
      .then((value) => {
        if (mounted) setState(value);
      })
      .catch(() => {
        // Onboarding must not turn a temporary API problem into a lockout.
        if (mounted) setFailed(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (failed || !state?.needs_onboarding) return <>{children}</>;

  async function finish(route?: string) {
    if (saving) return;
    setSaving(true);
    try {
      const next = await completeParticipationOnboarding();
      setState(next);
      if (route) window.location.hash = `#/${route}`;
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="era-page era-stagger"
      style={{
        minHeight: "100dvh",
        padding: "calc(1.25rem + env(safe-area-inset-top, 0px)) 1.15rem calc(1.5rem + env(safe-area-inset-bottom, 0px))",
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
      }}
    >
      <Card gradient style={{ padding: "1.35rem" }}>
        <MonoLabel tone="violet">ДОБРО ПОЖАЛОВАТЬ В ЭРА</MonoLabel>
        <h1 style={{ margin: ".45rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "clamp(2rem,10vw,3rem)", lineHeight: .98 }}>
          ЗДЕСЬ ИЗ УЧАСТНИКА<br />СТАНОВЯТСЯ ЛИДЕРОМ
        </h1>
        <p style={{ margin: ".85rem 0 0", color: "var(--era-text-secondary)", lineHeight: 1.5 }}>
          Не нужно изучать длинную инструкцию. В ЭРА рост строится через реальные действия: событие, задача, проект — и следующий уровень открывается по подтверждённому результату.
        </p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3,minmax(0,1fr))", gap: ".55rem" }}>
        {[
          ["01", "УЧАСТНИК", "Знакомишься и пробуешь"],
          ["02", "АКТИВНЫЙ", "Берёшь ответственность"],
          ["03", "ЛИДЕР", "Ведёшь людей и проекты"],
        ].map(([step, title, description]) => (
          <Card key={step} style={{ padding: ".8rem", minWidth: 0 }}>
            <MonoLabel>{step}</MonoLabel>
            <strong style={{ display: "block", marginTop: ".35rem", fontSize: ".78rem", overflowWrap: "anywhere" }}>{title}</strong>
            <span style={{ display: "block", marginTop: ".3rem", color: "var(--era-text-muted)", fontSize: ".68rem", lineHeight: 1.35 }}>{description}</span>
          </Card>
        ))}
      </div>

      <section style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
        <MonoLabel>С ЧЕГО НАЧАТЬ</MonoLabel>
        <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void finish("events")}>Посмотреть ближайшие события →</button>
        <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void finish("development")}>Открыть «Мой вектор» →</button>
        <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void finish("opportunities")}>Посмотреть возможности →</button>
      </section>

      <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void finish()} style={{ marginTop: "auto", width: "100%" }}>
        {saving ? "Сохраняем…" : "Начать"}
      </button>
    </div>
  );
}
