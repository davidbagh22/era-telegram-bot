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
  ACTIVE: "Активный",
  LIGHT: "Лёгкий",
  PAUSED: "Пауза",
  OBSERVER: "Наблюдатель",
  EXITED: "Вышел из текущего состава",
};

const STATE_LABELS: Record<ParticipationState["activity_state"], string> = {
  ADAPTATION: "Адаптация",
  ACTIVE: "В активной базе",
  COOLING: "Снижение активности",
  INACTIVE: "Неактивен",
  DORMANT: "Давно без активности",
  ARCHIVE_CANDIDATE: "Нужна сверка участия",
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
      <div style={{ padding: "0 1.25rem 1rem" }}>
        <Card onClick={() => setOpen(true)} style={{ padding: ".9rem 1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: ".8rem", alignItems: "center" }}>
            <div>
              <MonoLabel>РЕЖИМ УЧАСТИЯ</MonoLabel>
              <strong style={{ display: "block", marginTop: ".25rem" }}>{MODE_LABELS[state.participation_mode]}</strong>
              <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-muted)", fontSize: ".76rem" }}>
                {STATE_LABELS[state.activity_state]}{pauseText ? ` · до ${pauseText}` : ""}
              </span>
            </div>
            <span aria-hidden="true">→</span>
          </div>
        </Card>
      </div>

      <BottomSheet open={open} onClose={() => { setOpen(false); setConfirmExit(false); }} title="Режим участия">
        <div style={{ display: "flex", flexDirection: "column", gap: ".65rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-secondary)", lineHeight: 1.45 }}>
            Режим выбираете Вы. Состояние активности рассчитывает система по подтверждённым действиям — это две разные вещи.
          </p>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("ACTIVE")}>Активный · хочу включаться регулярно</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("LIGHT")}>Лёгкий · без регулярной нагрузки</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("PAUSED", { pauseMonths: 1 })}>Пауза на 1 месяц</button>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("PAUSED", { pauseMonths: 3 })}>Пауза на 3 месяца</button>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: ".5rem" }}>
            <input
              type="date"
              value={customDate}
              min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
              onChange={(event) => setCustomDate(event.target.value)}
              aria-label="Дата окончания паузы"
              style={{ minWidth: 0 }}
            />
            <button type="button" className="era-btn-secondary" disabled={saving || !customDate} onClick={() => void change("PAUSED", { pauseUntil: customDate })}>Поставить паузу</button>
          </div>
          <button type="button" className="era-btn-secondary" disabled={saving} onClick={() => void change("OBSERVER")}>Наблюдатель · без регулярных задач</button>

          {!confirmExit ? (
            <button type="button" className="era-btn-ghost" disabled={saving} onClick={() => setConfirmExit(true)}>Выйти из текущего состава</button>
          ) : (
            <Card style={{ padding: ".85rem" }}>
              <strong>Подтвердить выход?</strong>
              <p style={{ margin: ".35rem 0 .75rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>
                Профиль, баллы, портфолио и история сохранятся. Удаление персональных данных — отдельный процесс.
              </p>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: ".5rem" }}>
                <button type="button" className="era-btn-secondary" onClick={() => setConfirmExit(false)}>Отмена</button>
                <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void change("EXITED")}>Подтвердить</button>
              </div>
            </Card>
          )}
        </div>
      </BottomSheet>
    </>
  );
}
