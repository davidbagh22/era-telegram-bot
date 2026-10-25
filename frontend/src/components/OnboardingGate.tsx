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

const STEPS = [
  { number: "01", title: "Включайся", description: "События, задачи, проекты" },
  { number: "02", title: "Делай", description: "Получай реальный результат" },
  { number: "03", title: "Расти", description: "Новые роли и возможности" },
];

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

  async function finish() {
    if (saving) return;
    setSaving(true);
    try {
      setState(await completeParticipationOnboarding());
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="era-page era-stagger"
      style={{
        minHeight: "100dvh",
        padding: "calc(1.25rem + env(safe-area-inset-top, 0px)) 1rem calc(1.5rem + env(safe-area-inset-bottom, 0px))",
        display: "flex",
        flexDirection: "column",
        gap: "1.5rem",
      }}
    >
      <header style={{ paddingTop: "1rem" }}>
        <MonoLabel tone="violet">ЭРА</MonoLabel>
        <h1 style={{ margin: ".55rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "clamp(1.8rem,8vw,2.35rem)", lineHeight: 1.05 }}>
          Включайся. Делай. Расти.
        </h1>
        <p style={{ margin: ".7rem 0 0", color: "var(--era-text-secondary)", fontSize: "1rem", lineHeight: 1.5 }}>
          Здесь участие превращается в подтверждённый опыт, а опыт — в новые возможности.
        </p>
      </header>

      <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
        {STEPS.map((step) => (
          <Card key={step.number} style={{ padding: "1rem" }}>
            <div style={{ display: "grid", gridTemplateColumns: "2.5rem 1fr", gap: ".8rem", alignItems: "start" }}>
              <MonoLabel tone="violet">{step.number} ●</MonoLabel>
              <div>
                <strong style={{ display: "block", fontSize: "1.1rem" }}>{step.title}</strong>
                <span style={{ display: "block", marginTop: ".25rem", color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.45 }}>
                  {step.description}
                </span>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void finish()} style={{ marginTop: "auto", width: "100%", minHeight: 48 }}>
        {saving ? "Сохраняем…" : "Начать"}
      </button>
    </div>
  );
}
