import { useCallback, useState } from "react";
import { decideEraProApplication, fetchAdminEraProApplications, type EraProAdminApplication } from "../../api/eraPro";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { StatusBadge } from "../../components/StatusBadge";
import { useAsync } from "../../hooks/useAsync";

const DIRECTION_LABELS: Record<string, string> = {
  diplomacy: "Дипломатия",
  international_relations: "Международные отношения",
  entrepreneurship: "Предпринимательство",
  management: "Управление",
  public_speaking: "Публичные выступления",
  culture: "Культура",
  education: "Образование",
  media: "Медиа",
  social_projects: "Социальные проекты",
  project_work: "Проектная деятельность",
  other: "Другое",
};

function formatPoints(value: number) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function Answer({ label, text }: { label: string; text: string | null }) {
  return <div><strong style={{ display: "block", marginBottom: "0.3rem", fontSize: "0.78rem", color: "var(--era-text-muted)" }}>{label}</strong><p style={{ margin: 0, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{text || "—"}</p></div>;
}

function ApplicationCard({ application, busy, comment, onComment, onDecision }: {
  application: EraProAdminApplication;
  busy: boolean;
  comment: string;
  onComment: (value: string) => void;
  onDecision: (decision: "needs_info" | "approved" | "declined") => void;
}) {
  return (
    <Card style={{ borderLeft: "4px solid var(--era-violet)", display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
        <div>
          <MonoLabel tone="violet">ЭРА PRO · заявка #{application.id}</MonoLabel>
          <strong style={{ display: "block", marginTop: "0.28rem", fontSize: "1.05rem" }}>{application.full_name}</strong>
          <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>{application.username ? `@${application.username}` : `ID ${application.user_id}`} · {formatPoints(application.points)} баллов</p>
        </div>
        <StatusBadge label={application.status === "needs_info" ? "Нужно дополнить" : "На рассмотрении"} tone={application.status === "needs_info" ? "gold" : "violet"} />
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>{application.directions.map((key) => <span key={key} style={{ padding: "0.4rem 0.55rem", borderRadius: 999, background: "var(--era-surface-2)", border: "1px solid var(--era-border)", fontSize: "0.76rem" }}>{DIRECTION_LABELS[key] ?? key}</span>)}</div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
        <Answer label="Почему хочет попасть в ЭРА PRO" text={application.motivation} />
        <Answer label="Результат на 3–6 месяцев" text={application.target_result} />
        <Answer label="Чем полезен сообществу" text={application.community_value} />
        {application.portfolio_url && <div><strong style={{ display: "block", marginBottom: "0.3rem", fontSize: "0.78rem", color: "var(--era-text-muted)" }}>Проект / портфолио</strong><a href={application.portfolio_url} target="_blank" rel="noreferrer" style={{ overflowWrap: "anywhere" }}>{application.portfolio_url}</a></div>}
      </div>

      <div style={{ padding: "0.75rem", borderRadius: "var(--era-radius-md)", background: "var(--era-surface-2)" }}>
        <strong style={{ display: "block", marginBottom: "0.25rem" }}>Что проверить перед решением</strong>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.5 }}>Подтверждённую активность, историю участия, качество ответов, мотивацию и то, чем человек может усиливать закрытое сообщество.</p>
      </div>

      <textarea rows={3} value={comment} onChange={(event) => onComment(event.target.value)} placeholder="Комментарий — обязателен для запроса информации" />
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
        <button type="button" className="era-btn-primary" disabled={busy || application.status !== "submitted"} onClick={() => onDecision("approved")}>Принять</button>
        <button type="button" disabled={busy || application.status !== "submitted" || !comment.trim()} onClick={() => onDecision("needs_info")}>Запросить информацию</button>
        <button type="button" disabled={busy || application.status !== "submitted"} onClick={() => onDecision("declined")}>Отклонить</button>
      </div>
    </Card>
  );
}

export function AdminEraProScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminEraProApplications(), [refreshKey]);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);

  const decide = useCallback(async (applicationId: number, decision: "needs_info" | "approved" | "declined") => {
    setBusyId(applicationId);
    setError(null);
    try {
      await decideEraProApplication(applicationId, decision, comments[applicationId]);
      setComments((current) => ({ ...current, [applicationId]: "" }));
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить решение.");
    } finally {
      setBusyId(null);
    }
  }, [comments]);

  if (state.status === "loading") return <p style={{ color: "var(--era-text-muted)" }}>Загрузка заявок ЭРА PRO…</p>;
  if (state.status === "error") return <EmptyState text="Не удалось загрузить заявки ЭРА PRO." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
      <div><MonoLabel tone="violet">Закрытый уровень</MonoLabel><h2 style={{ margin: "0.3rem 0 0" }}>Заявки ЭРА PRO</h2><p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.82rem" }}>Здесь только участники, которые достигли порога 8 000 баллов и сами подали заявку.</p></div>
      {error && <p style={{ margin: 0, color: "var(--era-error)" }}>{error}</p>}
      {state.data.length === 0 ? <EmptyState text="Заявок ЭРА PRO на рассмотрении сейчас нет." /> : state.data.map((application) => <ApplicationCard key={application.id} application={application} busy={busyId === application.id} comment={comments[application.id] ?? ""} onComment={(value) => setComments((current) => ({ ...current, [application.id]: value }))} onDecision={(decision) => void decide(application.id, decision)} />)}
    </div>
  );
}