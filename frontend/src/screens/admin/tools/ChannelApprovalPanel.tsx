import { useCallback, useEffect, useState } from "react";
import {
  approveChannelPublicationToday,
  fetchChannelApprovalToday,
  type ChannelApprovalPreview,
} from "../../../api/channelApproval";
import { Card } from "../../../components/Card";

export function ChannelApprovalPanel() {
  const [preview, setPreview] = useState<ChannelApprovalPreview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      setPreview(await fetchChannelApprovalToday());
    } catch {
      setPreview(null);
      setError("Не удалось загрузить текст публикации на сегодня.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const approve = async () => {
    if (!preview || preview.target == null || preview.approved || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await approveChannelPublicationToday(
        preview.day,
        preview.target,
        preview.digest,
      );
      setNotice(
        result.already
          ? "Этот точный текст на сегодня уже был согласован."
          : "Публикация согласована. Планировщик отправит её только в согласованное окно, без повторов.",
      );
      await load();
    } catch {
      setError("Согласование не удалось. Обновите превью и попробуйте снова.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <Card>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
          Согласование действует только для точной даты (Москва), канала ЭРА и SHA-256 текста.
          Без согласования канал не получает новый пост. Бот-команда{" "}
          <code>/approve_channel_post</code> делает то же самое.
        </p>
      </Card>

      {error && (
        <Card>
          <p style={{ margin: 0, color: "var(--era-red)" }}>{error}</p>
          <button type="button" onClick={() => void load()} style={{ marginTop: "0.5rem" }}>
            Обновить
          </button>
        </Card>
      )}

      {notice && (
        <Card>
          <p style={{ margin: 0 }}>{notice}</p>
        </Card>
      )}

      {preview && (
        <Card>
          <p style={{ margin: "0 0 0.35rem", fontWeight: 700 }}>
            День: {preview.day}
            {preview.approved ? " · уже согласовано" : " · ожидает согласования"}
          </p>
          <p style={{ margin: "0 0 0.35rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
            Канал: {preview.target ?? "не настроен"}
          </p>
          <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>
            SHA-256: {preview.digest.slice(0, 16)}…
          </p>
          <pre
            style={{
              margin: 0,
              whiteSpace: "pre-wrap",
              fontFamily: "inherit",
              fontSize: "var(--era-text-sm)",
              lineHeight: 1.45,
            }}
          >
            {preview.preview}
          </pre>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.85rem", flexWrap: "wrap" }}>
            <button type="button" className="era-btn-secondary" disabled={busy} onClick={() => void load()}>
              Обновить превью
            </button>
            <button
              type="button"
              className="era-btn-primary"
              disabled={busy || preview.approved || preview.target == null}
              onClick={() => void approve()}
            >
              {preview.approved ? "Уже согласовано" : "Согласовать на сегодня"}
            </button>
          </div>
        </Card>
      )}
    </div>
  );
}
