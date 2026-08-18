import { useState } from "react";
import { Card } from "../components/Card";
import { MonoLabel } from "../components/MonoLabel";

interface OnboardingScreenProps {
  onDone: () => void;
}

// Community Verification ToR §36-46: exact copy for the existing 5 tabs
// (Главная/Проекты/События/Сообщество/Профиль) plus the "Мой вектор" card
// that's already prominent on Home and Profile -- no new navigation
// structure, just explaining what's already there.
const SECTIONS: { title: string; description: string }[] = [
  { title: "Главная", description: "Всё важное сейчас: ближайшее событие, активные задачи, прогресс и быстрые действия." },
  { title: "События", description: "Афиша ЭРА, программа, регистрация и твои ближайшие мероприятия." },
  { title: "Проекты", description: "Здесь идеи превращаются в реальные инициативы: участвуй в командах или создавай свои." },
  { title: "Сообщество", description: "Возможности, лидерборд и медиа — программы, предложения и способы включиться в ЭРА." },
  { title: "Профиль", description: "Твоя история внутри ЭРА: активность, баллы, достижения, портфолио и прогресс." },
];

export function OnboardingScreen({ onDone }: OnboardingScreenProps) {
  const [busy, setBusy] = useState(false);

  const handleDone = async () => {
    setBusy(true);
    try {
      await onDone();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="era-page" style={{ padding: "1.5rem 1.25rem calc(1.5rem + env(safe-area-inset-bottom))", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      <div>
        <MonoLabel tone="violet">ТЫ В ЭРА</MonoLabel>
        <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.85rem", fontWeight: 800, margin: "0.4rem 0 0" }}>
          Как устроена ЭРА
        </h1>
        <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)" }}>
          Здесь всё собрано вокруг твоего участия и роста.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "0.65rem" }}>
        {SECTIONS.map((section) => (
          <Card key={section.title} style={{ padding: "1rem" }}>
            <strong style={{ display: "block", fontSize: "1rem" }}>{section.title}</strong>
            <p style={{ margin: "0.35rem 0 0", color: "var(--era-text-muted)", fontSize: "0.875rem", lineHeight: 1.45 }}>
              {section.description}
            </p>
          </Card>
        ))}
      </div>

      <Card gradient style={{ padding: "1.1rem" }}>
        <MonoLabel tone="orange">МОЙ ВЕКТОР</MonoLabel>
        <strong style={{ display: "block", marginTop: "0.4rem", fontSize: "1.05rem" }}>
          Личное пространство для фокуса и развития
        </strong>
        <p style={{ margin: "0.45rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.875rem", lineHeight: 1.45 }}>
          Помогает замечать изменения, фиксировать цели и понимать, куда двигаться дальше. Личные
          ответы остаются личными. Открой его с Главной или из Профиля.
        </p>
      </Card>

      <button type="button" className="era-btn-primary" disabled={busy} onClick={handleDone}>
        Начать
      </button>
    </div>
  );
}
