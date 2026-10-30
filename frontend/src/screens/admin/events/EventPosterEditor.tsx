import { useEffect, useState } from "react";
import {
  fetchAdminEventPoster,
  fetchEventDraft,
  removeEventPoster,
  uploadEventPoster,
} from "../../../api/adminEvents";
import { describeActionError } from "../../../api/client";
import { Card } from "../../../components/Card";

const ACCEPTED_MIME = new Set(["image/jpeg", "image/png", "image/webp"]);
const MAX_POSTER_BYTES = 5 * 1024 * 1024;

interface Props {
  eventId: number;
  onBack: () => void;
}

interface PosterState {
  title: string;
  has_poster: boolean;
}

// The published-event editor changes only the poster bytes. It never calls
// publish, changes registration state, or sends a new announcement.
export function EventPosterEditor({ eventId, onBack }: Props) {
  const [event, setEvent] = useState<PosterState | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setEvent(null);
    setError(null);
    setSuccess(null);
    void fetchEventDraft(eventId)
      .then((result) => {
        if (active) setEvent({ title: result.title, has_poster: result.has_poster });
      })
      .catch((reason: unknown) => {
        if (active) setError(describeActionError(reason));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [eventId]);

  useEffect(() => {
    let active = true;
    let objectUrl: string | null = null;
    setPreviewUrl(null);
    if (event?.has_poster) {
      void fetchAdminEventPoster(eventId)
        .then((blob) => {
          if (!active) return;
          objectUrl = URL.createObjectURL(blob);
          setPreviewUrl(objectUrl);
        })
        .catch((reason: unknown) => {
          if (active) setError(describeActionError(reason));
        });
    }
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [eventId, event?.has_poster, revision]);

  const replacePoster = async (file: File | undefined) => {
    if (!file || busy || !event) return;
    setError(null);
    setSuccess(null);
    if (!ACCEPTED_MIME.has(file.type) || file.size > MAX_POSTER_BYTES || file.size === 0) {
      setError("Выберите JPG, PNG или WEBP размером от 1 байта до 5 МБ.");
      return;
    }
    setBusy(true);
    try {
      const result = await uploadEventPoster(eventId, file);
      setEvent({ title: result.title, has_poster: result.has_poster });
      setRevision((value) => value + 1);
      setSuccess("Афиша обновлена. Регистрации и мероприятие сохранены.");
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusy(false);
    }
  };

  const deletePoster = async () => {
    if (!event?.has_poster || busy) return;
    if (!window.confirm("Удалить только изображение афиши? Мероприятие, регистрации и баллы сохранятся.")) return;
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const result = await removeEventPoster(eventId);
      setEvent({ title: result.title, has_poster: result.has_poster });
      setRevision((value) => value + 1);
      setSuccess("Изображение афиши удалено. Мероприятие осталось в системе.");
    } catch (reason) {
      setError(describeActionError(reason));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".75rem" }}>
      <button type="button" disabled={busy} onClick={onBack} style={{ alignSelf: "flex-start" }}>← К списку мероприятий</button>
      <Card gradient>
        <h2 style={{ margin: 0 }}>Редактировать афишу</h2>
        <p style={{ margin: ".4rem 0 0", color: "var(--era-text-secondary)" }}>
          {event?.title ?? "Загружаем мероприятие…"}
        </p>
      </Card>
      {loading ? (
        <Card>Загружаем афишу…</Card>
      ) : !event ? (
        <Card><p role="alert">Не удалось открыть мероприятие. {error}</p></Card>
      ) : (
        <Card>
          <p style={{ marginTop: 0, color: "var(--era-text-muted)" }}>
            Изменение изображения не публикует новый анонс и не меняет участников, баллы или статус мероприятия.
          </p>
          {previewUrl && <img src={previewUrl} alt="Текущая афиша" style={{ display: "block", width: "100%", maxHeight: 320, objectFit: "contain", borderRadius: ".8rem", marginBottom: ".75rem" }} />}
          {event.has_poster && !previewUrl && <p>Загружаем изображение…</p>}
          {!event.has_poster && <p>У мероприятия пока нет изображения афиши.</p>}
          <label style={{ display: "block", cursor: busy ? "wait" : "pointer" }}>
            <strong>{event.has_poster ? "Заменить афишу" : "Загрузить афишу"}</strong>
            <input
              aria-label="Выбрать изображение афиши"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={busy}
              onChange={(change) => {
                const file = change.target.files?.[0];
                change.target.value = "";
                void replacePoster(file);
              }}
              style={{ display: "block", marginTop: ".5rem", maxWidth: "100%" }}
            />
          </label>
          {event.has_poster && (
            <button type="button" disabled={busy} onClick={() => void deletePoster()} style={{ marginTop: ".75rem" }}>
              Удалить только изображение
            </button>
          )}
          {error && <p role="alert" style={{ color: "var(--era-error)" }}>{error}</p>}
          {success && <p role="status" style={{ color: "var(--era-success)" }}>{success}</p>}
        </Card>
      )}
    </div>
  );
}
