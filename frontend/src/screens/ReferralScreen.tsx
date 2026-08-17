import { useCallback } from "react";
import { fetchReferralSummary } from "../api/referrals";
import { Card } from "../components/Card";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import { useAsync } from "../hooks/useAsync";

interface ReferralScreenProps {
  onBack: () => void;
}

async function copyText(value: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.appendChild(input);
  input.select();
  document.execCommand("copy");
  input.remove();
}

export function ReferralScreen({ onBack }: ReferralScreenProps) {
  const state = useAsync(() => fetchReferralSummary(), []);
  const toast = useToast();

  const share = useCallback(async () => {
    if (state.status !== "ready") return;
    const data = state.data;
    try {
      if (navigator.share) {
        await navigator.share({
          title: "Присоединяйся к ЭРА",
          text: data.share_text,
          url: data.invite_url || undefined,
        });
        return;
      }
      await copyText(data.share_text);
      toast.show("Приглашение скопировано", "success");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      toast.show("Не удалось поделиться. Скопируйте код вручную.", "attention");
    }
  }, [state, toast]);

  if (state.status === "loading") {
    return (
      <div className="era-page" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="era-page" style={{ padding: "1.25rem" }}>
        <button type="button" onClick={onBack} style={{ marginBottom: "1rem" }}>← Назад</button>
        <StatusBanner title="Не удалось открыть приглашение" description="Закройте и снова откройте этот раздел." />
      </div>
    );
  }

  const data = state.data;
  const monthlyPercent = Math.min(
    100,
    Math.round((data.monthly_earned_points / Math.max(1, data.monthly_cap)) * 100),
  );
  const copyCode = async () => {
    await copyText(data.code);
    toast.show("Код скопирован", "success");
  };
  const copyLink = async () => {
    await copyText(data.invite_url || data.share_text);
    toast.show(data.invite_url ? "Ссылка скопирована" : "Приглашение скопировано", "success");
  };

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>

      <div>
        <p style={{ margin: "0 0 0.35rem", color: "var(--era-red)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase", letterSpacing: ".08em" }}>
          Расти вместе
        </p>
        <h1 style={{ margin: 0, fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)" }}>Пригласить друга</h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55 }}>
          Поделитесь ссылкой и кодом. Баллы приходят только за реальные подтверждённые действия — автоматически.
        </p>
      </div>

      <Card gradient style={{ position: "relative", overflow: "hidden" }}>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 700 }}>ВАШ КОД</p>
        <div style={{ marginTop: "0.55rem", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "clamp(2rem, 11vw, 3.1rem)", fontWeight: 900, letterSpacing: ".16em", lineHeight: 1 }}>
          {data.code}
        </div>
        <p style={{ margin: "0.75rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
          Друг вводит эти 6 цифр во время регистрации.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.65rem", marginTop: "1rem" }}>
          <button type="button" onClick={copyCode}>Скопировать код</button>
          <button type="button" onClick={copyLink}>Скопировать ссылку</button>
        </div>
        <button type="button" className="era-btn-primary" onClick={share} style={{ width: "100%", marginTop: "0.65rem" }}>
          Отправить приглашение
        </button>
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Как это работает</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "2.25rem minmax(0, 1fr) auto", gap: "0.75rem", alignItems: "center" }}>
              <div aria-hidden="true" style={{ width: "2.25rem", height: "2.25rem", borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-tint-red)", fontWeight: 900 }}>1</div>
              <div>
                <strong>Регистрация + общий чат</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Друг регистрируется, вводит ваш код и вступает в общий чат после одобрения.</p>
              </div>
              <strong style={{ whiteSpace: "nowrap" }}>+{data.registration_points_each} каждому</strong>
            </div>
          </Card>
          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "2.25rem minmax(0, 1fr) auto", gap: "0.75rem", alignItems: "center" }}>
              <div aria-hidden="true" style={{ width: "2.25rem", height: "2.25rem", borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-tint-red)", fontWeight: 900 }}>2</div>
              <div>
                <strong>Первое мероприятие</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>После первого реально посещённого мероприятия система подтверждает следующий этап.</p>
              </div>
              <strong style={{ whiteSpace: "nowrap" }}>+{data.first_event_points_each} каждому</strong>
            </div>
          </Card>
          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "2.25rem minmax(0, 1fr) auto", gap: "0.75rem", alignItems: "center" }}>
              <div aria-hidden="true" style={{ width: "2.25rem", height: "2.25rem", borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-tint-red)", fontWeight: 900 }}>3</div>
              <div>
                <strong>Активный участник</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>Когда приглашённый дорастает до статуса «Активный участник», система начисляет третий бонус автоматически.</p>
              </div>
              <strong style={{ whiteSpace: "nowrap" }}>+{data.active_points_each} каждому</strong>
            </div>
          </Card>
        </div>
      </section>

      <Card>
        <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "baseline" }}>
          <div>
            <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Лимит месяца</p>
            <strong style={{ display: "block", marginTop: "0.35rem", fontSize: "var(--era-text-xl)" }}>
              {data.monthly_earned_points} / {data.monthly_cap}
            </strong>
          </div>
          <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", textAlign: "right" }}>
            до {data.per_invitee_cap} за полный путь одного друга
          </span>
        </div>
        <div
          aria-label={`Реферальный лимит использован на ${monthlyPercent}%`}
          style={{ height: "0.45rem", marginTop: "0.85rem", borderRadius: "999px", background: "var(--era-border)", overflow: "hidden" }}
        >
          <div style={{ width: `${monthlyPercent}%`, height: "100%", borderRadius: "inherit", background: "var(--era-red)", transition: "width 180ms ease" }} />
        </div>
      </Card>

      <Card>
        <p style={{ margin: "0 0 0.75rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Ваш результат</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.9rem" }}>
          <div><strong style={{ fontSize: "var(--era-text-2xl)" }}>{data.invited_count}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>ввели ваш код</span></div>
          <div><strong style={{ fontSize: "var(--era-text-2xl)" }}>{data.first_event_count}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>пришли на событие</span></div>
          <div><strong style={{ fontSize: "var(--era-text-2xl)" }}>{data.active_count}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>стали активными</span></div>
          <div><strong style={{ fontSize: "var(--era-text-2xl)" }}>{data.earned_points}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>заработано баллов</span></div>
        </div>
      </Card>

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.5 }}>
        Код привязывается к новичку один раз. Самоприглашение и повторное начисление за одно и то же действие не работают. Лимит {data.monthly_cap} применяется к реферальному заработку приглашающего за календарный месяц.
      </p>
    </div>
  );
}
