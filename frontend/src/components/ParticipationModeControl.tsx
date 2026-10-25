import { useEffect, useMemo, useState } from "react";
import {
  fetchParticipation,
  updateParticipationMode,
  type ParticipationState,
} from "../api/participation";
import { BottomSheet } from "./BottomSheet";
import { Card } from "./Card";
import { MonoLabel } from "./MonoLabel";

const MODE_LABELS: Record<ParticipationState["participation_mode"], string> = {
  ACTIVE: "Обычный",
  LIGHT: "Лёгкий",
  PAUSED: "Пауза",
  OBSERVER: "Наблюдаю",
  EXITED: "Участие завершено",
};

export function ParticipationModeControl() {
  const [visible, setVisible] = useState(() => window.location.hash.includes("profile"));
  const [state, setState] = useState<ParticipationState | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [customDate, setCustomDate] = useState("");
  const [confirmExit, setConfirmExit] = useState(false);

  useEffect(() => {
    const sync = () => setVisible(window.location.hash.includes("profile"));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    if (!visible || state) return;
    void fetchParticipation().then(setState).catch(() => undefined);
  }, [visible, state]);

  const pauseText = useMemo(() => {
    if (!state?.pause_until) return null;
    const date = new Date(`${state.pause_until}T00:00:00`);
    return Number.isNaN(date.getTime()) ? state.pause_until : date.toLocaleDateString("ru-RU");
  }, [state]);

  if (!visible || !state) return null;

  async function change(
    mode: ParticipationState["participation_mode"],
    options: { pauseMonths?: 1 | 3; pauseUntil?: string } = {},
  ) {
    if (saving) return;
    setSaving(true);
    try {
      const next = await updateParticipationMode(mode, options);
      setState(next);
      setConfirmExit(false);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <div style={{ padding: "0 1rem 1rem" }}>
        <Card onClick={() => setOpen(true)} style={{ padding: ".9rem 1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", alignItems: "center" }}>
            <div>
              <MonoLabel>МОЙ ТЕМП</MonoLabel>
              <strong style={{ display: "block", marginTop: ".25rem" }}>{MODE_LABELS[state.participation_mode]}</strong>
              {pauseText && (
                <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-muted)", fontSize: ".75rem" }}>
                  До {pauseText}
                </span>
              )}
            </div>
            <span aria-hidden="true">→</span>
          </div>
        </Card>
      </div>

      <BottomSheet open={open} onClose={() => { setOpen(false); setConfirmExit(false); }} title="Мой темп">
        <div style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: ".9rem", lineHeight: 1.5 }}>
            Выбери темп, который подходит тебе сейчас. История, баллы и подтверждённый опыт сохраняются.
          </p>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("ACTIVE")}>Обычный · включаюсь регулярно</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("LIGHT")}>Лёгкий · без регулярной нагрузки</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("OBSERVER")}>Наблюдаю · без текущих задач</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("PAUSED", { pauseMonths: 1 })}>Пауза на 1 месяц</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("PAUSED", { pauseMonths: 3 })}>Пауза на 3 месяца</button>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: ".5rem" }}>
            <input
              type="date"
              value={customDate}
              min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
              onChange={(event) => setCustomDate(event.target.value)}
              aria-label="Дата окончания паузы"
              style={{ minWidth: 0, minHeight: 44 }}
            />
            <button type="button" className="era-btn-secondary" disabled={saving || !customDate} onClick={() => void change("PAUSED", { pauseUntil: customDate })}>Пауза до даты</button>
          </div>

          <div style={{ borderTop: "1px solid var(--era-border)", marginTop: ".35rem", paddingTop: ".8rem" }}>
            {!confirmExit ? (
              <button type="button" className="era-btn-ghost" disabled={saving} onClick={() => setConfirmExit(true)}>Завершить участие</button>
            ) : (
              <Card style={{ padding: ".85rem" }}>
                <strong>Завершить участие в текущем составе?</strong>
                <p style={{ margin: ".35rem 0 .75rem", color: "var(--era-text-muted)", fontSize: ".8rem", lineHeight: 1.45 }}>
                  Профиль, баллы, портфолио и история сохранятся. Вернуться можно отдельно через команду ЭРА.
                </p>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
                  <button type="button" className="era-btn-secondary" onClick={() => setConfirmExit(false)}>Отмена</button>
                  <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void change("EXITED")}>Завершить</button>
                </div>
              </Card>
            )}
          </div>
        </div>
      </BottomSheet>
    </>
  );
}
