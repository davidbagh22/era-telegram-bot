import { useCallback } from "react";
import { fetchReferralSummary, prepareReferralShareMessage } from "../api/referrals";
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

function cleanFallbackShareText(text: string, inviteUrl: string): string {
  if (!inviteUrl) return text.trim();
  return text
    .replace(inviteUrl, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function telegramShareUrl(url: string, text: string): string {
  return `https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`;
}

function pointsBadge(points: number) {
  return (
    <strong
      style={{
        whiteSpace: "nowrap",
        color: "var(--era-violet)",
        background: "var(--era-tint-violet)",
        borderRadius: 999,
        padding: "0.36rem 0.58rem",
        fontSize: "var(--era-text-sm)",
      }}
    >
      +{points}
    </strong>
  );
}

export function ReferralScreen({ onBack }: ReferralScreenProps) {
  const state = useAsync(() => fetchReferralSummary(), []);
  const toast = useToast();

  const share = useCallback(async () => {
    if (state.status !== "ready") return;
    const data = state.data;
    const webApp = window.Telegram?.WebApp;
    const fallbackText = cleanFallbackShareText(data.share_text, data.invite_url);

    try {
      if (webApp?.shareMessage) {
        try {
          const prepared = await prepareReferralShareMessage();
          webApp.shareMessage(prepared.id);
          return;
        } catch {
          // Older clients or temporary Bot API failures continue to the clean fallback below.
        }
      }

      if (webApp?.openTelegramLink && data.invite_url) {
        webApp.openTelegramLink(telegramShareUrl(data.invite_url, fallbackText));
        return;
      }

      if (navigator.share) {
        await navigator.share({
          title: "Присоединяйся к ЭРА",
          text: fallbackText,
          url: data.invite_url || undefined,
        });
        return;
      }

      await copyText(data.invite_url || data.share_text);
      toast.show(data.invite_url ? "Ссылка скопирована" : "Приглашение скопировано", "success");
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      toast.show("Не удалось поделиться. Скопируйте ссылку вручную.", "attention");
    }
  }, [state, toast]);

  if (state.status === "loading") {
    return (
      <div
        className="era-page"
        style={{
          padding: "1.25rem 1rem var(--era-page-bottom-safe)",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Назад</button>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="era-page" style={{ padding: "1.25rem 1rem var(--era-page-bottom-safe)" }}>
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
    <div
      className="era-page era-stagger"
      style={{
        padding: "1.25rem 1rem var(--era-page-bottom-safe)",
        display: "flex",
        flexDirection: "column",
        gap: "1.2rem",
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem" }}>
        <button type="button" onClick={onBack} style={{ minHeight: 44, alignSelf: "flex-start" }}>← Назад</button>
        <ContextHelp mode="user" topic="referral" inline />
      </div>

      <header>
        <p
          style={{
            margin: "0 0 0.35rem",
            color: "var(--era-violet)",
            fontSize: "var(--era-text-xs)",
            fontWeight: 800,
            textTransform: "uppercase",
            letterSpacing: ".08em",
          }}
        >
          Приглашения
        </p>
        <h1
          style={{
            margin: 0,
            maxWidth: "18ch",
            fontFamily: "var(--era-font-display)",
            fontSize: "clamp(1.8rem, 7vw, 2.2rem)",
            lineHeight: 1.08,
            letterSpacing: "-0.035em",
          }}
        >
          Пригласи тех, кому здесь будет интересно
        </h1>
        <p style={{ margin: "0.7rem 0 0", color: "var(--era-text-muted)", lineHeight: 1.55, maxWidth: "34rem" }}>
          Делись ЭРА с людьми, которым действительно близки проекты, развитие и сильное окружение. Баллы появляются только за реальное участие.
        </p>
      </header>

      <Card gradient>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: "0.8rem" }}>
          <div>
            <p
              style={{
                margin: 0,
                color: "var(--era-text-muted)",
                fontSize: "var(--era-text-xs)",
                fontWeight: 800,
                textTransform: "uppercase",
              }}
            >
              Персональная ссылка
            </p>
            <p style={{ margin: "0.28rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>
              Код приглашения: <strong style={{ color: "var(--era-text)" }}>{data.code}</strong>
            </p>
          </div>
        </div>

        <div
          style={{
            marginTop: "0.75rem",
            padding: "0.8rem 0.9rem",
            borderRadius: "var(--era-radius-md)",
            background: "color-mix(in srgb, var(--era-surface) 78%, transparent)",
            border: "1px solid color-mix(in srgb, var(--era-violet) 12%, var(--era-border))",
            overflowWrap: "anywhere",
            fontSize: "var(--era-text-sm)",
            lineHeight: 1.4,
          }}
        >
          {data.invite_url || `Код: ${data.code}`}
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
            gap: "0.65rem",
            marginTop: "0.8rem",
          }}
        >
          <button type="button" onClick={copyLink}>Копировать</button>
          <button type="button" className="era-btn-primary" onClick={share}>Поделиться</button>
        </div>
      </Card>

      <section>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: "0.8rem", marginBottom: "0.7rem" }}>
          <h2 style={{ margin: 0, fontSize: "var(--era-text-xl)" }}>Как начисляются баллы</h2>
          <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", whiteSpace: "nowrap" }}>
            до +{data.per_invitee_cap}
          </span>
        </div>

        <div style={{ display: "grid", gap: "0.7rem" }}>
          <Card>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "2.35rem minmax(0, 1fr) auto",
                gap: "0.75rem",
                alignItems: "center",
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  width: "2.35rem",
                  height: "2.35rem",
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  background: "var(--era-tint-violet)",
                  color: "var(--era-violet)",
                  fontWeight: 900,
                }}
              >
                1
              </div>
              <div style={{ minWidth: 0 }}>
                <strong>Регистрация одобрена</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45 }}>
                  Человек зарегистрировался по твоей ссылке и прошёл проверку анкеты.
                </p>
              </div>
              {pointsBadge(data.registration_points_each)}
            </div>
          </Card>

          <Card>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "2.35rem minmax(0, 1fr) auto",
                gap: "0.75rem",
                alignItems: "center",
              }}
            >
              <div
                aria-hidden="true"
                style={{
                  width: "2.35rem",
                  height: "2.35rem",
                  borderRadius: "50%",
                  display: "grid",
                  placeItems: "center",
                  background: "var(--era-tint-violet)",
                  color: "var(--era-violet)",
                  fontWeight: 900,
                }}
              >
                2
              </div>
              <div style={{ minWidth: 0 }}>
                <strong>Первое участие подтверждено</strong>
                <p style={{ margin: "0.2rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)", lineHeight: 1.45 }}>
                  Приглашённый впервые реально участвует в мероприятии или проекте ЭРА.
                </p>
              </div>
              {pointsBadge(data.first_event_points_each)}
            </div>
          </Card>
        </div>

        <p style={{ margin: "0.7rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", lineHeight: 1.5 }}>
          За одного приглашённого можно получить максимум +{data.per_invitee_cap} баллов.
        </p>
      </section>

      <Card>
        <p
          style={{
            margin: "0 0 0.85rem",
            color: "var(--era-text-muted)",
            fontSize: "var(--era-text-xs)",
            fontWeight: 800,
            textTransform: "uppercase",
          }}
        >
          Твои приглашения
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
            gap: "0.5rem",
            textAlign: "center",
          }}
        >
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)", lineHeight: 1 }}>{data.invited_count}</strong>
            <span style={{ display: "block", marginTop: "0.35rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Приглашены</span>
          </div>
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)", lineHeight: 1 }}>{data.registered_count}</strong>
            <span style={{ display: "block", marginTop: "0.35rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Одобрены</span>
          </div>
          <div>
            <strong style={{ display: "block", fontSize: "var(--era-text-xl)", lineHeight: 1 }}>{data.first_event_count}</strong>
            <span style={{ display: "block", marginTop: "0.35rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Активны</span>
          </div>
        </div>

        <div
          style={{
            marginTop: "1rem",
            paddingTop: "0.9rem",
            borderTop: "1px solid var(--era-border)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
          }}
        >
          <span style={{ color: "var(--era-text-muted)" }}>Заработано</span>
          <strong style={{ fontSize: "var(--era-text-lg)" }}>+{data.earned_points} баллов</strong>
        </div>
      </Card>

      <div
        style={{
          padding: "0.85rem 0.95rem",
          borderRadius: "var(--era-radius-md)",
          background: "var(--era-surface-2)",
          border: "1px solid var(--era-border)",
          color: "var(--era-text-muted)",
          fontSize: "var(--era-text-xs)",
          lineHeight: 1.5,
        }}
      >
        Баллы начисляются автоматически. Самоприглашение, повторная регистрация и повторное начисление за одно действие не учитываются.
      </div>
    </div>
  );
}
