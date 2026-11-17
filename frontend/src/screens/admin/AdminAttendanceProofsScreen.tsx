import { useCallback, useEffect, useState } from "react";
import {
  approveAttendanceProof,
  attendanceProofPhotoBlobUrl,
  fetchPendingAttendanceProofs,
  rejectAttendanceProof,
  type AdminAttendanceProof,
} from "../../api/eventAttendance";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBanner } from "../../components/StatusBanner";
import { useToast } from "../../components/Toast";

function ProofPhoto({ url }: { url: string }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    void attendanceProofPhotoBlobUrl(url)
      .then((next) => {
        if (!active) {
          URL.revokeObjectURL(next);
          return;
        }
        objectUrl = next;
        setSrc(next);
      })
      .catch(() => {
        if (active) setSrc(null);
      });
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [url]);
  if (!src) {
    return (
      <div style={{ minHeight: 160, borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)", display: "grid", placeItems: "center", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
        Фото загружается…
      </div>
    );
  }
  return (
    <img
      src={src}
      alt="Фото с места"
      style={{ width: "100%", maxHeight: 280, objectFit: "contain", borderRadius: "var(--era-radius-control)", background: "var(--era-surface-2)" }}
    />
  );
}

export function AdminAttendanceProofsScreen() {
  const [items, setItems] = useState<AdminAttendanceProof[] | null>(null);
  const [error, setError] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [comments, setComments] = useState<Record<number, string>>({});
  const toast = useToast();

  const refresh = useCallback(async () => {
    try {
      setItems(await fetchPendingAttendanceProofs());
      setError(false);
    } catch {
      setError(true);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const decide = async (proofId: number, action: "approve" | "reject") => {
    setBusyId(proofId);
    try {
      if (action === "approve") await approveAttendanceProof(proofId);
      else await rejectAttendanceProof(proofId, comments[proofId] ?? "");
      toast.show(action === "approve" ? "Участие подтверждено" : "Фото отклонено", "success");
      await refresh();
    } catch {
      toast.show("Не удалось сохранить решение", "error");
    } finally {
      setBusyId(null);
    }
  };

  if (error) {
    return (
      <div style={{ display: "grid", gap: "0.75rem" }}>
        <StatusBanner title="Не удалось загрузить фото-подтверждения" description="Обновите и попробуйте снова." />
        <button type="button" onClick={() => void refresh()}>Повторить</button>
      </div>
    );
  }
  if (!items) return <p style={{ color: "var(--era-text-muted)" }}>Загружаем очередь…</p>;
  if (items.length === 0) return <EmptyState text="Очередь фото-подтверждений пуста." />;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
        Подтверждение даёт баллы за визит и автоматически выпускает сертификат участника.
      </p>
      {items.map((item) => (
        <Card key={item.id}>
          <strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.user_name}</strong>
          <p style={{ margin: "0.35rem 0 0.75rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
            {item.event_title}
          </p>
          <ProofPhoto url={item.photo_url} />
          <textarea
            rows={2}
            placeholder="Комментарий при отклонении (необязательно)"
            value={comments[item.id] ?? ""}
            onChange={(event) => setComments((prev) => ({ ...prev, [item.id]: event.target.value }))}
            style={{ width: "100%", marginTop: "0.75rem" }}
          />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", marginTop: "0.65rem" }}>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busyId === item.id}
              onClick={() => void decide(item.id, "approve")}
            >
              Подтвердить
            </button>
            <button
              type="button"
              disabled={busyId === item.id}
              onClick={() => void decide(item.id, "reject")}
              style={{ color: "var(--era-error)" }}
            >
              Отклонить
            </button>
          </div>
        </Card>
      ))}
    </div>
  );
}
