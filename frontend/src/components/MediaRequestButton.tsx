import { useState } from "react";
import { requestEventMedia, requestProjectMedia } from "../api/media";

interface MediaRequestButtonProps {
  sourceType: "event" | "project";
  sourceId: number;
}

export function MediaRequestButton({ sourceType, sourceId }: MediaRequestButtonProps) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const request = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const result = sourceType === "event"
        ? await requestEventMedia(sourceId, "full")
        : await requestProjectMedia(sourceId, "full");
      setDone(true);
      setStatus(
        result.status === "open"
          ? "Медиа-пакет создан: текст, дизайн, фото, видео, монтаж и Stories разложены на задачи."
          : "Запрос уже есть в Media Desk — второй пакет не создаём.",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "request_failed";
      setStatus(
        message.includes("403") || message.includes("forbidden")
          ? "Запросить Медиа может автор проекта/мероприятия или участник Media Desk."
          : "Не удалось создать медиа-пакет. Попробуйте ещё раз.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "grid", gap: "0.45rem" }}>
      <button
        type="button"
        className="era-btn-primary"
        disabled={busy || done}
        onClick={() => void request()}
        style={{ width: "100%" }}
      >
        {busy ? "Создаём медиа-пакет…" : done ? "Медиа-пакет запрошен ✓" : "Запросить Медиа"}
      </button>
      {status ? (
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>
          {status}
        </p>
      ) : null}
    </div>
  );
}
