import { useState } from "react";
import { previewRegistrantMessage, sendRegistrantMessage } from "../../../api/adminEvents";
import { describeActionError } from "../../../api/client";
import { Card } from "../../../components/Card";

export function RegistrantMessagePanel({ eventId }: { eventId: number }) {
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof previewRegistrantMessage>> | null>(null);
  const [report, setReport] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    setReport("");
    try {
      if (preview) {
        const result = await sendRegistrantMessage(eventId, message, preview.confirmation);
        setReport(`Отправлено: ${result.sent}. Уже доставлено: ${result.already_sent}. Без подтверждения: ${result.failed}.`);
        setMessage("");
        setPreview(null);
      } else {
        setPreview(await previewRegistrantMessage(eventId, message));
      }
    } catch (error) {
      setReport(describeActionError(error));
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }

  return <Card><details><summary>Написать зарегистрированным</summary>
    <label>Сообщение<textarea disabled={busy} rows={4} maxLength={3500} value={message}
      onChange={e => { setMessage(e.target.value); setPreview(null); setReport(""); }} /></label>
    {preview && <><p style={{ whiteSpace: "pre-wrap" }}>{preview.message}</p><p>Получателей: {preview.count}</p></>}
    <button disabled={busy || !message.trim() || preview?.count === 0} onClick={() => void submit()}>
      {busy ? "Подождите…" : preview ? "Подтвердить отправку" : "Предпросмотр"}
    </button>
    {report && <p role="status">{report}</p>}
  </details></Card>;
}
