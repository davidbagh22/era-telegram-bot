import { useCallback } from "react";
import { fetchReferralSummary } from "../api/referrals";
import { Card } from "../components/Card";
import { ContextHelp } from "../components/ContextHelp";
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
      if (window.Telegram?.WebApp?.openTelegramLink) {
        const shareUrl = new URL("https://t.me/share/url");
        shareUrl.searchParams.set("url", data.invite_url);
        shareUrl.searchParams.set("text", data.share_text);
        window.Telegram.WebApp.openTelegramLink(shareUrl.toString());
        return;
      }
      if (navigator.share) {
        await navigator.share({
          title: "Присоединяйся к ЭРА",
          text: data.share_text,
          url: data.invite_url || undefined,
        });
        return;
      }
      await copyText(data.invite_url || data.share_text);
      toast.show("Ссылка скопирована", "success");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      toast.show("Не удалось поделиться. Скопируйте ссылку вручную.", "attention");
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
        <StatusBanner title="Не удалось открыть приглашения" description="Попробуйте открыть раздел ещё раз." />
      </div>
    );
  }

  const data = state.data;
  const copyLink = async () => {
    await copyText(data.invite_url || data.share_text);
    toast.show(data.invite_url ? "Ссылка скопирована" : "Приглашение скопировано", "success");
  };

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>

      <header>
        <p style={{ margin: "0 0 0.35rem", color: "var(--era-violet)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase", letterSpacing: ".08em" }}>
          Приглашения
        </p>
        <h1 style={{ margin: 0, fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)" }}>
          Пригласи человека, которому здесь действительно будет интересно
        </h1>
        <p style={{ margin: "0.65rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55 }}>
          Баллы начисляются не за отправленные ссылки. Они появляются, когда приглашённый тобой человек действительно становится частью ЭРА.
        </p>
      </header>

      <Card gradient>
        <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Ваша персональная ссылка
        </p>
        <div style={{ marginTop: "0.65rem", padding: "0.75rem", borderRadius: "var(--era-radius-md)", background: "rgba(255,255,255,.5)", overflowWrap: "anywhere", fontSize: "var(--era-text-sm)" }}>
          {data.invite_url || `Код: ${data.code}`}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.65rem", marginTop: "0.8rem" }}>
          <button type="button" onClick={copyLink}>Скопировать</button>
          <button type="button" className="era-btn-primary" onClick={share}>Поделиться</button>
        </div>
      </Card>

      <section>
        <h2 style={{ margin: "0 0 0.7rem", fontSize: "var(--era-text-xl)" }}>Когда появляются баллы</h2>
        <div style={{ display: "grid", gap: "0.7rem" }}>
          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "2.1rem minmax(0, 1fr) auto", gap: "0.75rem", alignItems: "center" }}>
              <div aria-hidden="true" style={{ width: "2.1rem", height: "2.1rem", borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-tint-violet)", fontWeight: 900 }}>1</div>
              <div>
                <strong>Регистрация одобрена</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  Человек зарегистрировался по вашей ссылке, прошёл анкету и получил статус APPROVED.
                </p>
              </div>
              <strong style={{ whiteSpace: "nowrap" }}>+{data.registration_points_each}</strong>
            </div>
          </Card>

          <Card>
            <div style={{ display: "grid", gridTemplateColumns: "2.1rem minmax(0, 1fr) auto", gap: "0.75rem", alignItems: "center" }}>
              <div aria-hidden="true" style={{ width: "2.1rem", height: "2.1rem", borderRadius: "50%", display: "grid", placeItems: "center", background: "var(--era-tint-violet)", fontWeight: 900 }}>2</div>
              <div>
                <strong>Первое подтверждённое участие</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
                  После первого подтверждённого участия в мероприятии или проекте ЭРА.
                </p>
              </div>
              <strong style={{ whiteSpace: "nowrap" }}>+{data.first_event_points_each}</strong>
            </div>
          </Card>
        </div>
        <p style={{ margin: "0.7rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>
          Максимум +{data.per_invitee_cap} баллов за одного человека. Баллы получает пригласивший участник; они не списываются.
        </p>
      </section>

      <Card>
        <p style={{ margin: "0 0 0.8rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>
          Статистика
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: "0.65rem", textAlign: "center" }}>
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)" }}>{data.invited_count}</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Приглашено</span>
          </div>
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)" }}>{data.registered_count}</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Вступили</span>
          </div>
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)" }}>{data.first_event_count}</strong>
            <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Стали активными</span>
          </div>
        </div>
        <div style={{ marginTop: "1rem", paddingTop: "0.9rem", borderTop: "1px solid var(--era-border)", display: "flex", justifyContent: "space-between", gap: "1rem" }}>
          <span style={{ color: "var(--era-text-muted)" }}>Получено</span>
          <strong>+{data.earned_points} баллов</strong>
        </div>
      </Card>

      <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.5 }}>
        Переход по ссылке и вступление в чат сами по себе ничего не начисляют. Самоприглашение, повторный аккаунт и повторное начисление за одно действие блокируются на backend.
      </p>

      <ContextHelp mode="user" topic="referral" />
    </div>
  );
}
