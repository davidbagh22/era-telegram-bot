import { useCallback, useEffect, useState } from "react";
import {
  downloadAdminCareerEvidence,
  fetchAdminCareerItems,
  fetchAdminRecommendations,
  reviewAdminCareerItem,
  reviewAdminRecommendation,
} from "../../api/career";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonCard } from "../../components/Skeleton";
import { StatusBanner } from "../../components/StatusBanner";
import { useToast } from "../../components/Toast";
import type { AdminCareerItem, AdminRecommendation } from "../../types/career";

function openBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function AdminCareerScreen() {
  const [items, setItems] = useState<AdminCareerItem[]>([]);
  const [recommendations, setRecommendations] = useState<AdminRecommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const toast = useToast();

  const refresh = useCallback(async () => {
    try {
      const [nextItems, nextRecommendations] = await Promise.all([
        fetchAdminCareerItems(),
        fetchAdminRecommendations(),
      ]);
      setItems(nextItems);
      setRecommendations(nextRecommendations);
      setDrafts((prev) => {
        const next = { ...prev };
        for (const request of nextRecommendations) {
          if (next[request.id] === undefined) next[request.id] = request.draft_text;
        }
        return next;
      });
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const reviewItem = async (item: AdminCareerItem, decision: "approve" | "reject") => {
    const key = `item-${item.id}`;
    setBusy(key);
    try {
      await reviewAdminCareerItem(item.id, decision, comments[item.id]);
      await refresh();
      toast.show(decision === "approve" ? "Достижение подтверждено" : "Возвращено участнику", "success");
    } catch {
      toast.show("Не удалось сохранить решение", "error");
    } finally {
      setBusy(null);
    }
  };

  const reviewRecommendation = async (request: AdminRecommendation, decision: "approve" | "reject") => {
    const key = `rec-${request.id}`;
    setBusy(key);
    try {
      await reviewAdminRecommendation(request.id, decision, drafts[request.id], comments[request.id]);
      await refresh();
      toast.show(decision === "approve" ? "Официальное письмо утверждено" : "Запрос отклонён", "success");
    } catch {
      toast.show("Не удалось сохранить решение", "error");
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <div style={{ display: "grid", gap: "0.75rem" }}><SkeletonCard /><SkeletonCard /></div>;
  if (error) return <StatusBanner title="Не удалось загрузить проверки" description="Проверьте доступ portfolio.review и обновите страницу." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      <section>
        <div style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Достижения на проверке</h2>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>Подтверждение ЭРА ставится только после проверки файла или источника.</p>
        </div>
        {items.length === 0 ? <EmptyState text="Нет достижений, ожидающих проверки." /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {items.map((item) => (
              <Card key={item.id}>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>{item.user_name}</p>
                <h3 style={{ margin: "0.25rem 0 0" }}>{item.title}</h3>
                {item.organization && <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>{item.organization}</p>}
                {item.description && <p style={{ margin: "0.65rem 0 0" }}>{item.description}</p>}
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.75rem" }}>
                  {item.has_file && (
                    <button type="button" disabled={busy !== null} onClick={() => void (async () => {
                      try { openBlob(await downloadAdminCareerEvidence(item.id), item.file_name || "evidence"); }
                      catch { toast.show("Не удалось открыть файл", "error"); }
                    })()}>Открыть файл</button>
                  )}
                  {item.url && <a href={item.url} target="_blank" rel="noreferrer">Открыть источник ↗</a>}
                </div>
                <textarea
                  rows={2}
                  placeholder="Комментарий участнику (особенно при отказе)"
                  value={comments[item.id] ?? ""}
                  onChange={(event) => setComments((prev) => ({ ...prev, [item.id]: event.target.value }))}
                  style={{ width: "100%", marginTop: "0.75rem" }}
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.65rem" }}>
                  <button type="button" disabled={busy !== null} onClick={() => void reviewItem(item, "reject")} style={{ color: "var(--era-error)" }}>Не подтверждать</button>
                  <button type="button" className="era-btn-primary" disabled={busy !== null} onClick={() => void reviewItem(item, "approve")}>✓ Подтвердить ЭРА</button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section>
        <div style={{ marginBottom: "0.75rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Официальные рекомендации</h2>
          <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)" }}>Текст подготовлен из подтверждённых фактов. Перед выдачей его можно отредактировать.</p>
        </div>
        {recommendations.length === 0 ? <EmptyState text="Нет рекомендаций, ожидающих утверждения." /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            {recommendations.map((request) => (
              <Card key={request.id}>
                <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800 }}>{request.user_name} · {request.purpose}</p>
                <textarea
                  rows={10}
                  value={drafts[request.id] ?? request.draft_text}
                  onChange={(event) => setDrafts((prev) => ({ ...prev, [request.id]: event.target.value }))}
                  style={{ width: "100%", marginTop: "0.7rem" }}
                />
                <textarea
                  rows={2}
                  placeholder="Комментарий при отклонении"
                  value={comments[request.id] ?? ""}
                  onChange={(event) => setComments((prev) => ({ ...prev, [request.id]: event.target.value }))}
                  style={{ width: "100%", marginTop: "0.65rem" }}
                />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.65rem" }}>
                  <button type="button" disabled={busy !== null} onClick={() => void reviewRecommendation(request, "reject")} style={{ color: "var(--era-error)" }}>Отклонить</button>
                  <button type="button" className="era-btn-primary" disabled={busy !== null} onClick={() => void reviewRecommendation(request, "approve")}>Утвердить письмо</button>
                </div>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
