import { useState } from "react";
import { BottomSheet } from "../../components/BottomSheet";

const RULE_GROUPS = [
  {
    title: "В приложении",
    items: [
      "+5 — первый активный вход за день",
      "+20 — 7 активных дней подряд",
      "+50 — полностью заполненный профиль, один раз",
      "+30 — ежемесячный check-in «Моего вектора»",
      "+10 — weekly check-in, максимум 4/месяц",
      "+15 — постановка личной цели, максимум 2/месяц",
      "+25 — завершение личной цели, максимум 2/месяц",
      "+5 — полезный материал/обновление, максимум 5/месяц",
      "+10 — регистрация на мероприятие",
    ],
  },
  {
    title: "Мероприятия",
    items: [
      "+100 — подтверждённое посещение",
      "+25/час — волонтёрство, максимум 200 за активность",
      "+150 — помощь в организации",
      "+250 — организатор",
      "+300 — координатор",
      "+150 — спикер/модератор",
      "+100–200 — медиасопровождение",
    ],
  },
  {
    title: "Задания",
    items: [
      "+40 — простое",
      "+80 — среднее",
      "+150 — сложное",
      "+200 — milestone / критическая задача",
    ],
  },
  {
    title: "Проекты",
    items: [
      "+50 — первое подтверждённое действие",
      "+120 — milestone",
      "+250 — успешное завершение проекта участником",
      "+150 дополнительно — Project Lead",
      "+50 — идея принята",
      "+250 — инициатива реализована",
    ],
  },
  {
    title: "Социальная и волонтёрская деятельность",
    items: [
      "+25/час — подтверждённое волонтёрство",
      "+100–200 — участие в социальной инициативе",
      "+250 — организация инициативы",
      "+250 — реализованный общественный результат",
    ],
  },
  {
    title: "Медиа",
    items: [
      "+50 — простой материал",
      "+100 — значимый материал",
      "+150 — официальный/сложный материал",
      "+200 — полное медиасопровождение проекта/события",
    ],
  },
  {
    title: "Внешние связи",
    items: [
      "+150 — представление ЭРА на внешнем мероприятии",
      "+100 — рабочая партнёрская встреча",
      "+200 — достигнутая договорённость",
      "+250 — реализованный партнёрский результат",
    ],
  },
  {
    title: "Наставничество",
    items: [
      "+75 — подопечный выполнил первую задачу",
      "+150 — стал активным участником",
      "+200 — получил первую ответственность",
      "+250 — вырос до лидерской/project-роли",
    ],
  },
  {
    title: "Приглашения",
    items: [
      "+50 — приглашённый зарегистрирован и одобрен",
      "+75 — посетил первое мероприятие",
      "+125 — стал активным участником",
      "Максимум 250 за человека",
      "Максимум 750 referral-баллов в месяц",
    ],
  },
] as const;

const RESPONSIBILITY = [
  "Участник — ×1.00",
  "Куратор — ×1.05",
  "Project Lead / лидер — ×1.10",
  "Руководитель — ×1.15",
  "Коэффициент действует только на задачи в рамках роли.",
  "+150/месяц — подтверждённый результат лидера месяца.",
] as const;

export function PointsRulesSheet() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        style={{ width: "100%", textAlign: "left", padding: "0.9rem 1rem" }}
      >
        <strong style={{ display: "block" }}>Как получать баллы</strong>
        <span style={{ display: "block", marginTop: "0.2rem", color: "var(--era-text-muted)", fontSize: "0.8rem" }}>
          Все действия, лимиты и коэффициенты
        </span>
      </button>

      <BottomSheet open={open} onClose={() => setOpen(false)} title="Как получать баллы">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem", maxHeight: "68vh", overflowY: "auto", paddingBottom: "0.5rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "0.82rem", lineHeight: 1.45 }}>
            Баллы показывают подтверждённую активность. Для документов они являются порогом и не списываются.
          </p>

          {RULE_GROUPS.map((group) => (
            <details key={group.title} style={{ border: "1px solid var(--era-border)", borderRadius: "var(--era-radius-control)", padding: "0.75rem" }}>
              <summary style={{ cursor: "pointer", fontWeight: 750 }}>{group.title}</summary>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.42rem", marginTop: "0.65rem" }}>
                {group.items.map((item) => (
                  <div key={item} style={{ fontSize: "0.82rem", lineHeight: 1.4 }}>{item}</div>
                ))}
              </div>
            </details>
          ))}

          <details style={{ border: "1px solid var(--era-border)", borderRadius: "var(--era-radius-control)", padding: "0.75rem" }}>
            <summary style={{ cursor: "pointer", fontWeight: 750 }}>Коэффициент ответственности</summary>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.42rem", marginTop: "0.65rem" }}>
              {RESPONSIBILITY.map((item) => (
                <div key={item} style={{ fontSize: "0.82rem", lineHeight: 1.4 }}>{item}</div>
              ))}
            </div>
          </details>
        </div>
      </BottomSheet>
    </>
  );
}
