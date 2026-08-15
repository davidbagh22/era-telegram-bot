import { useEffect, useRef, useState } from "react";
import { createEventDraft, saveEventDraft } from "../../../api/adminEvents";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { SkeletonCard } from "../../../components/Skeleton";
import { AdminEventCreatePanel } from "./AdminEventCreatePanel";

interface SuggestedEventCreatePanelProps {
  suggestedTopic?: string | null;
  onPrepared?: () => void;
}

export function SuggestedEventCreatePanel({ suggestedTopic, onPrepared }: SuggestedEventCreatePanelProps) {
  const started = useRef<string | null>(null);
  const [prepared, setPrepared] = useState<{ id: number; topic: string } | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    const topic = suggestedTopic?.trim();
    if (!topic || started.current === `${topic}:${retryKey}`) return;
    started.current = `${topic}:${retryKey}`;
    let cancelled = false;
    setLoading(true);
    setError(false);
    void createEventDraft()
      .then((draft) => saveEventDraft(draft.id, {
        title: `${topic}: новое событие`,
        category: topic,
        wizard_step: 1,
      }))
      .then((draft) => {
        if (cancelled) return;
        setPrepared({ id: draft.id, topic });
        onPrepared?.();
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [onPrepared, retryKey, suggestedTopic]);

  return (
    <div style={{ display: "grid", gap: "0.75rem" }}>
      {loading && <SkeletonCard />}
      {error && <EmptyState title="Не удалось подготовить черновик" description="Тема не потеряна. Повторите — публикации и рассылки без подтверждения не будет." actionLabel="Повторить" onAction={() => { started.current = null; setRetryKey((value) => value + 1); }} />}
      {prepared && (
        <Card style={{ borderColor: "rgba(62,166,107,.24)", background: "var(--era-tint-success)", boxShadow: "none" }}>
          <strong>Черновик подготовлен</strong>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>
            Тема «{prepared.topic}» уже внесена в новый черновик #{prepared.id}. Она остаётся предложением: администратор может полностью изменить её перед публикацией.
          </p>
        </Card>
      )}
      <AdminEventCreatePanel />
    </div>
  );
}
