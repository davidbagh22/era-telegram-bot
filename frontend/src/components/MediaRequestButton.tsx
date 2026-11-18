import { useEffect, useState } from "react";
import { requestEventMedia, requestProjectMedia } from "../api/media";

interface MediaRequestButtonProps {
  sourceType: "event" | "project";
  sourceId: number;
  /** When true, start expanded (leader media panel). Default: collapsed. */
  defaultOpen?: boolean;
}

const PACKAGES: { key: "photo" | "reels" | "full"; label: string; hint: string }[] = [
  { key: "photo", label: "Фото", hint: "Съёмка и отбор кадров" },
  { key: "reels", label: "Рилс", hint: "Короткое видео + монтаж" },
  { key: "full", label: "Полный", hint: "Текст, дизайн, фото, видео, сторис" },
];

export function MediaRequestButton({ sourceType, sourceId, defaultOpen = false }: MediaRequestButtonProps) {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [packageType, setPackageType] = useState<"photo" | "reels" | "full">("full");
  const [dueLocal, setDueLocal] = useState("");
  const [open, setOpen] = useState(defaultOpen);

  useEffect(() => {
    setBusy(false);
    setStatus(null);
    setDone(false);
    setPackageType("full");
    setDueLocal("");
    setOpen(defaultOpen);
  }, [sourceType, sourceId, defaultOpen]);

  const request = async () => {
    setBusy(true);
    setStatus(null);
    try {
      const dueAt = dueLocal ? new Date(dueLocal).toISOString() : undefined;
      const result = sourceType === "event"
        ? await requestEventMedia(sourceId, packageType, dueAt)
        : await requestProjectMedia(sourceId, packageType, dueAt);
      setDone(true);
      const pack = PACKAGES.find((item) => item.key === packageType)?.label ?? packageType;
      setStatus(
        result.status === "open"
          ? `Готово: пакет «${pack}» ушёл команде Медиа. Они увидят задачу в панели редакции${dueAt ? " со сроком" : ""}.`
          : "Такой пакет уже есть в редакции — второй не создаём.",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "request_failed";
      setStatus(
        message.includes("403") || message.includes("forbidden")
          ? "Запросить медиа может автор или участник редакции Медиа."
          : "Не удалось создать запрос. Попробуйте ещё раз.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <details
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
      style={{
        borderRadius: "var(--era-radius-md, 1rem)",
        border: "1px solid var(--era-border)",
        background: "var(--era-surface)",
        overflow: "hidden",
      }}
    >
      <summary
        style={{
          listStyle: "none",
          cursor: "pointer",
          padding: "0.85rem 0.95rem",
          display: "grid",
          gap: "0.2rem",
        }}
      >
        <strong style={{ fontSize: "0.95rem" }}>Заказать медиа команде</strong>
        <span style={{ color: "var(--era-text-muted)", fontSize: "0.8rem", lineHeight: 1.4 }}>
          Для автора и редакции: фото, рилс или полный пакет. Не публикация в канал.
        </span>
      </summary>
      <div style={{ display: "grid", gap: "0.65rem", padding: "0 0.95rem 0.95rem" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.84rem", lineHeight: 1.45 }}>
          Выберите пакет → укажите срок → отправьте. Команда Медиа получит задачу и сделает материал.
        </p>
        <div style={{ display: "grid", gap: "0.35rem" }}>
          <span style={{ fontSize: "0.78rem", color: "var(--era-text-muted)", fontWeight: 700 }}>1. Пакет</span>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "0.4rem" }}>
            {PACKAGES.map((pack) => (
              <button
                key={pack.key}
                type="button"
                aria-pressed={packageType === pack.key}
                disabled={busy || done}
                onClick={() => setPackageType(pack.key)}
                style={{
                  minHeight: "3.1rem",
                  borderRadius: "0.75rem",
                  border: `1px solid ${packageType === pack.key ? "var(--era-teal)" : "var(--era-border)"}`,
                  background: packageType === pack.key ? "color-mix(in srgb, var(--era-teal) 14%, var(--era-surface))" : "var(--era-surface)",
                  textAlign: "left",
                  padding: "0.45rem 0.55rem",
                }}
              >
                <strong style={{ display: "block", fontSize: "0.86rem" }}>{pack.label}</strong>
                <span style={{ display: "block", marginTop: 2, fontSize: "0.68rem", color: "var(--era-text-muted)", lineHeight: 1.25 }}>{pack.hint}</span>
              </button>
            ))}
          </div>
        </div>
        <label style={{ display: "grid", gap: "0.3rem", fontSize: "0.78rem", color: "var(--era-text-muted)", fontWeight: 700 }}>
          2. Срок для редакции
          <input
            type="datetime-local"
            value={dueLocal}
            disabled={busy || done}
            onChange={(event) => setDueLocal(event.target.value)}
            style={{
              minHeight: "2.75rem",
              borderRadius: "0.75rem",
              border: "1px solid var(--era-border)",
              background: "var(--era-surface)",
              color: "var(--era-text)",
              padding: "0.5rem 0.65rem",
              fontFamily: "var(--era-font-body)",
            }}
          />
        </label>
        <button
          type="button"
          className="era-btn-primary"
          disabled={busy || done}
          onClick={() => void request()}
          style={{ width: "100%" }}
        >
          {busy ? "Отправляем…" : done ? "Запрос отправлен ✓" : "3. Отправить в Медиа"}
        </button>
        {status ? (
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.78rem", lineHeight: 1.4 }}>
            {status}
          </p>
        ) : null}
      </div>
    </details>
  );
}
