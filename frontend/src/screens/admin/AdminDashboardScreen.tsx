import { useState } from "react";
import { downloadAnalyticsSectionTable, downloadFullAnalyticsReport, fetchAdminAnalyticsDetails,
  fetchEraEfficiency, fetchOrganizationHealth, fetchAnalyticsV2, checkAnalyticsSources, fetchAnalyticsReports,
  type AnalyticsDetailSection, type HealthMetric, type TelegramAnalyticsSource } from "../../api/adminAnalytics";
import { fetchAdminAnalyticsSummary } from "../../api/client";
import { fetchMediaAnalytics } from "../../api/media";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { StatusBadge } from "../../components/StatusBadge";
import { useToast } from "../../components/Toast";
import { useAsync } from "../../hooks/useAsync";
import type { AnalyticsSummary } from "../../types/admin";
import "./adminAnalytics.css";

const SECTION_META: Record<
  AnalyticsDetailSection,
  { label: string; description: string; value: keyof AnalyticsSummary; accent: string }
> = {
  users: {
    label: "Участники",
    description: "Люди, статусы и динамика базы",
    value: "total_users",
    accent: "var(--era-red)",
  },
  events: {
    label: "Мероприятия",
    description: "Все события ЭРА",
    value: "events",
    accent: "var(--era-gold-ink)",
  },
  projects: {
    label: "Проекты",
    description: "Инициативы и проектная воронка",
    value: "projects",
    accent: "var(--era-red-bright)",
  },
  contacts: {
    label: "Организации",
    description: "Партнёрская база",
    value: "contacts",
    accent: "var(--era-blue)",
  },
  goals: {
    label: "Цели",
    description: "Цели организации и направлений",
    value: "goals",
    accent: "var(--era-gold)",
  },
};

const STATUS_LABELS: Record<string, string> = {
  approved: "Одобрено",
  pending: "Ожидает",
  needs_info: "Нужны данные",
  rejected: "Отклонено",
  draft: "Черновик",
  published: "Опубликовано",
  registration_open: "Регистрация открыта",
  registration_closed: "Регистрация закрыта",
  active: "Активно",
  initial_review: "Первичная проверка",
  venue_review: "Согласование площадки",
  needs_revision: "Нужна доработка",
  in_progress: "В работе",
  completed: "Завершено",
  done: "Готово",
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function DetailView({ section, onBack }: { section: AnalyticsDetailSection; onBack: () => void }) {
  const state = useAsync(() => fetchAdminAnalyticsDetails(section), [section]);
  const meta = SECTION_META[section];
  const toast = useToast();
  const [downloading, setDownloading] = useState(false);

  const downloadTable = async () => {
    setDownloading(true);
    try {
      saveBlob(await downloadAnalyticsSectionTable(section), `ERA_${section}.xlsx`);
    } catch {
      toast.show("Не удалось собрать Excel-таблицу.", "error");
    } finally {
      setDownloading(false);
    }
  };


  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Аналитика</button>
      <Card gradient>
        <p style={{ margin: 0, opacity: 0.72, fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Раздел аналитики</p>
        <h2 style={{ margin: "0.2rem 0 0", fontSize: "var(--era-text-2xl)" }}>{meta.label}</h2>
        <p style={{ margin: "0.35rem 0 0", opacity: 0.84 }}>{meta.description}</p>
      </Card>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        <button type="button" disabled={downloading} onClick={() => void downloadTable()}>↓ XLSX</button>
        <button type="button" onClick={onBack}>Обзор и PDF →</button>
      </div>
      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить записи." />}
      {state.status === "ready" && (
        <>
          <Card style={{ padding: "0.75rem 0.9rem", background: "var(--era-surface-2)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: "0.75rem" }}>
              <strong>Записей в системе</strong>
              <strong style={{ fontFamily: "var(--era-font-display)", fontSize: "1.6rem" }}>{state.data.total}</strong>
            </div>
          </Card>
          {state.data.items.length === 0 ? <EmptyState text="Записей пока нет." /> : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              {state.data.items.map((item) => (
                <Card key={`${section}-${item.id}`} style={{ padding: "0.8rem 0.9rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <strong style={{ display: "block", overflowWrap: "anywhere" }}>{item.title}</strong>
                      {item.subtitle && <span style={{ display: "block", marginTop: "0.25rem", color: "var(--era-text-muted)", fontSize: "0.78rem", overflowWrap: "anywhere" }}>{item.subtitle}</span>}
                    </div>
                    {item.status && <StatusBadge label={STATUS_LABELS[item.status] ?? item.status} tone="neutral" />}
                  </div>
                </Card>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

type AnalyticsTab = "Обзор" | "Люди" | "Деятельность" | "Команда" | "Возможности" | "Отчёты";
export type AnalyticsAction = "people" | "applications" | "events" | "projects" | "tasks" | "offers";
const TABS: AnalyticsTab[] = ["Обзор", "Люди", "Деятельность", "Команда", "Возможности", "Отчёты"];
const DATA_LABELS: Record<string, string> = { valid: "Данные за период", insufficient: "Частичное покрытие", unavailable: "Источник недоступен", stale: "Проверка устарела" };
function categoryTab(category: string): AnalyticsTab {
  if (/Люди|Вовлечённость/.test(category)) return "Люди";
  if (/События|Проекты|Исполнение/.test(category)) return "Деятельность";
  if (/Рост|Карьер|Возможности|Партнёр|Экосистем/.test(category)) return "Возможности";
  return "Команда";
}
function dateLabel(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU", { timeZone: "Asia/Yerevan" }) : "Ещё нет";
}
function DailyChart({ title, days }: { title: string; days: TelegramAnalyticsSource["daily"] }) {
  const max = Math.max(1, ...days.map((day) => day.value ?? day.observed));
  return <figure className="analytics-chart">
    <figcaption>{title}</figcaption>
    <svg viewBox="0 0 360 110" role="img" aria-label={`${title}. Максимум ${max}. Данные по дням доступны ниже.`}>
      <text x="0" y="12" className="analytics-axis">{max}</text><text x="0" y="92" className="analytics-axis">0</text>
      <line x1="25" y1="90" x2="357" y2="90" stroke="currentColor" opacity=".25" />
      {days.map((day, i) => { const value = day.value ?? day.observed; const width = 330 / Math.max(days.length, 1); return <rect key={day.date}
        x={26 + i * width} y={90 - value / max * 70} width={Math.max(.4, width - 1)} height={value / max * 70}
        fill="var(--era-violet, #632cff)" opacity={day.value === null ? .35 : .9}>
        <title>{day.date}: {value}{day.value === null ? " учтено, покрытие неполное" : ""}</title></rect>; })}
    </svg>
    <div className="analytics-chart-dates"><span>{days[0]?.date}</span><span>{days[days.length - 1]?.date}</span></div>
    <details><summary>Числа по дням · светлый цвет означает неполное покрытие</summary>
      <dl className="analytics-daily-values">{days.map((day) => <div key={day.date}><dt>{day.date}</dt><dd>{day.value ?? `${day.observed} учтено · частично`}</dd></div>)}</dl>
    </details>
  </figure>;
}
function SourceCard({ source, compare }: { source: TelegramAnalyticsSource; compare: boolean }) {
  return <Card style={{ padding: ".85rem" }}>
    <div className="analytics-source-title"><h3>{source.label}</h3><span className={`analytics-state analytics-state-${source.data_state}`}>{DATA_LABELS[source.data_state] ?? "Нет данных"}</span></div>
    <strong className="analytics-number">{source.value ?? (source.observed_value > 0 ? `${source.observed_value} учтено` : "Нет данных")}</strong>
    {compare && <p>{source.delta === null ? "Сравнение пока недоступно: нет полного предыдущего периода." : `${source.delta > 0 ? "+" : ""}${source.delta} к предыдущему равному периоду (${source.previous_value}).`}</p>}
    <p>{source.explanation}</p>
    <details><summary>Источник и покрытие</summary><p>Сбор начат: {dateLabel(source.started_at)}. Непрерывное покрытие: {dateLabel(source.coverage_since)}.</p>
      <p>Учтено с начала сбора: {source.total_observed}. Последнее событие: {dateLabel(source.last_event_at)}. Проверка прав: {dateLabel(source.checked_at)}.</p><p>{source.history_note}</p>
    </details>
    <DailyChart title={`${source.label} · по дням`} days={source.daily} />
  </Card>;
}

export function AdminDashboardScreen({ onAction }: { onAction?: (action: AnalyticsAction) => void }) {
  const [tab, setTab] = useState<AnalyticsTab>("Обзор");
  const [period, setPeriod] = useState("30");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [compare, setCompare] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [busy, setBusy] = useState<"pdf" | "xlsx" | "sources" | null>(null);
  const [selectedSection, setSelectedSection] = useState<AnalyticsDetailSection | null>(null);
  const toast = useToast();
  const validDates = period !== "custom" || Boolean(start && end && start <= end);
  const snapshot = useAsync(() => {
    if (!validDates) return Promise.resolve(null);
    return fetchAnalyticsV2(period === "custom" ? 30 : Number(period), period === "custom" ? start : undefined, period === "custom" ? end : undefined);
  }, [period, start, end, refresh]);
  const health = useAsync(() => fetchOrganizationHealth(), []);
  const efficiency = useAsync(() => fetchEraEfficiency(), []);
  const analytics = useAsync(() => fetchAdminAnalyticsSummary(), []);
  const media = useAsync(() => fetchMediaAnalytics(), []);
  const reports = useAsync(() => fetchAnalyticsReports(), [refresh]);
  const data = snapshot.status === "ready" ? snapshot.data : null;
  const metricGroups = new Map<string, HealthMetric[]>();
  if (health.status === "ready") for (const metric of health.data.metrics) {
    const values = metricGroups.get(metric.category) ?? []; values.push(metric); metricGroups.set(metric.category, values);
  }
  const download = async (format: "pdf" | "xlsx") => {
    if (!data || busy) return;
    setBusy(format);
    try {
      const blob = await downloadFullAnalyticsReport("custom", data.start, data.end, format);
      saveBlob(blob, format === "xlsx" ? "ERA_full_report.xlsx" : `ERA_analytics_${data.start}_${data.end}.pdf`);
      toast.show("Отчёт сформирован.", "success"); setRefresh((value) => value + 1);
    } catch { toast.show("Не удалось собрать отчёт. Попробуйте ещё раз.", "error"); }
    finally { setBusy(null); }
  };
  const checkSources = async () => {
    setBusy("sources");
    try { await checkAnalyticsSources(); setRefresh((value) => value + 1); }
    catch { toast.show("Не удалось проверить источники Telegram.", "error"); }
    finally { setBusy(null); }
  };
  if (selectedSection) return <DetailView section={selectedSection} onBack={() => setSelectedSection(null)} />;
  return <div className="era-analytics analytics-v2">
    <header><p className="era-analytics-eyebrow">ЭРА · УПРАВЛЕНИЕ</p><h2>ЭРА одним взглядом</h2></header>
    <section className="analytics-toolbar" aria-label="Период и отчёты">
      <label htmlFor="analytics-report-period">Период отчёта<select id="analytics-report-period" value={period} onChange={(e) => setPeriod(e.target.value)}>
        <option value="7">7 дней</option><option value="30">30 дней</option><option value="90">90 дней</option><option value="custom">Свои даты</option>
      </select></label>
      {period === "custom" && <div className="era-analytics-dates"><label>С даты<input aria-label="Начало периода" type="date" max={end || undefined} value={start} onChange={(e) => setStart(e.target.value)} /></label><label>По дату<input aria-label="Конец периода" type="date" min={start || undefined} value={end} onChange={(e) => setEnd(e.target.value)} /></label></div>}
      <label className="analytics-compare"><input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} /> Сравнить с предыдущим равным периодом</label>
      <div className="era-analytics-export-actions"><button className="era-btn-primary" disabled={!validDates || !data || busy !== null} onClick={() => void download("pdf")}>{busy === "pdf" ? "Готовим PDF…" : "↓ Скачать отчёт PDF"}</button><button disabled={!data || busy !== null} onClick={() => void download("xlsx")}>{busy === "xlsx" ? "Готовим Excel…" : "Excel"}</button></div>
      {!validDates && <p role="status">Укажите начало и конец периода по порядку.</p>}
      {data && <small>{data.start} — {data.end} · обновлено {dateLabel(data.updated_at)}. Остальные показатели подписаны своими окнами.</small>}
    </section>
    <div className="analytics-tabs" role="tablist" aria-label="Разделы аналитики">{TABS.map((name) => <button key={name} role="tab" aria-selected={tab === name} aria-controls="analytics-tab-panel" tabIndex={tab === name ? 0 : -1} onKeyDown={(event) => { if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) { event.preventDefault(); const index = event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : (TABS.indexOf(name) + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length; setTab(TABS[index]); (event.currentTarget.parentElement?.children[index] as HTMLButtonElement)?.focus(); } }} onClick={() => setTab(name)}>{name}</button>)}</div>
    <section id="analytics-tab-panel" role="tabpanel" aria-label={tab}>
      {snapshot.status === "loading" && <p role="status">Обновляем показатели…</p>}
      {snapshot.status === "error" && <EmptyState text="Не удалось получить данные за период. Значения не подменяются нулями." />}
      {(tab === "Обзор" || tab === "Люди") && data && <section><h3>Главное</h3><div className="analytics-kpis">{data.metrics.map((metric) => <Card key={metric.id} style={{ padding: ".8rem", minWidth: 0 }}><strong className="analytics-number">{metric.value ?? "Нет данных"}</strong><h4>{metric.label}</h4><small>{metric.period}</small>{compare && metric.delta !== null && <p>{metric.delta > 0 ? "+" : ""}{metric.delta} · ранее {metric.previous_value}</p>}<details><summary>Как считается</summary><p>{metric.explanation}</p>{metric.denominator !== null && <p>База: {metric.denominator} человек.</p>}</details></Card>)}</div></section>}
      {tab === "Обзор" && data && <><div className="analytics-sources">{data.sources.map((source) => <SourceCard source={source} key={source.id} compare={compare} />)}</div><button disabled={busy !== null} onClick={() => void checkSources()}>{busy === "sources" ? "Проверяем…" : "Проверить права и подключение Telegram"}</button></>}
      {tab === "Обзор" && health.status === "ready" && <>
        <section><h3>Требует внимания</h3>{health.data.risks.length ? <ul>{health.data.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <p>По доступным правилам отдельных сигналов нет.</p>}
          <small>Источник: факты и правила платформы; это не оценка всей деятельности ЭРА.</small>
        </section>
        <Card><h3>Опросный пульс</h3><strong className="analytics-number">{health.data.pulse_suppressed || health.data.pulse === null ? "Недостаточно данных" : `${health.data.pulse}/100`}</strong><p>Ответили {health.data.pulse_sample_size} человек · охват {health.data.pulse_coverage}% текущего состава.</p><p>{health.data.pulse_coverage < 30 ? "Низкий охват: результат не представляет всё сообщество." : "Показатель отражает ответы доступной выборки."}</p><details><summary>Методика и ограничения</summary><p>{health.data.period_label}. При выборке меньше 5 человек агрегат скрыт.</p><p>{health.data.data_note}</p></details></Card>
      </>}
      {tab === "Обзор" && onAction && <section><h3>Быстрые действия</h3><div className="analytics-actions">{([['tasks','Открыть задания'],['events','Открыть мероприятия'],['projects','Открыть проекты'],['applications','Рассмотреть заявки']] as const).map(([action,label]) => <button key={action} onClick={() => onAction(action)}>{label} →</button>)}</div></section>}
      {tab !== "Обзор" && tab !== "Отчёты" && <section><h3>Все показатели</h3><p className="analytics-note">Периоды 7/30/90 дней и текущие срезы указаны в названиях и пояснениях. Это не пересчёт всех метрик на выбранные даты.</p>{Array.from(metricGroups).filter(([category]) => categoryTab(category) === tab).map(([category, metrics]) => <details key={category} className="analytics-metric-group"><summary>{category} · {metrics.length} показателей</summary>{metrics.map((metric) => <div className="analytics-metric" key={metric.key}><strong>{metric.label}</strong><span>{metric.value === null || metric.data_state === "unavailable" ? "Нет данных" : metric.display}</span><small>{metric.period} · {metric.note}</small>{metric.denominator !== undefined && metric.denominator !== null && <small>{metric.unit === "rating" ? `Отзывов: ${metric.denominator}` : `Числитель: ${metric.numerator ?? "—"}; знаменатель: ${metric.denominator}`}</small>}</div>)}</details>)}</section>}
      {tab === "Люди" && data && <Card><h3>Приток по подтверждённым одобрениям</h3><p>Первые одобрения среди текущего состава. Старые записи без аудита не восстановлены; график не является историей общего состава.</p><DailyChart title="Новые участники по дням" days={data.member_growth} /></Card>}
      {tab === "Команда" && media.status === "ready" && <Card><h3>Контент-план и задачи медиа</h3><p>Опубликовано по контент-плану: {media.data.published}. Все публикации канала считаются отдельно в «Обзоре».</p><p>Подтверждённо выполнено задач: {media.data.tasks_completed} из {media.data.tasks_created}.</p><p>Вышло вовремя: {media.data.on_time_rate === null ? "Нет публикаций со сроком" : `${media.data.on_time_rate}%`}.</p></Card>}
      {tab === "Команда" && efficiency.status === "ready" && <details className="analytics-metric-group"><summary>Условный операционный индекс · методика</summary><p>Это индекс действий, зафиксированных в платформе, а не объективная оценка организации.</p><p>Вовлечённость — 45%, выпуск — 35%, отзывы — 20%. При отсутствии отзывов первые веса: 56,25% и 43,75%. Целевые ориентиры: 4 события и 2 проекта в месяц.</p><p>{data?.metrics.find((item) => item.id === "roster")?.value ? `${efficiency.data.score}/100` : "Нет базы для расчёта"}. {efficiency.data.period_label}</p><p>{efficiency.data.data_note}</p></details>}
      {tab === "Обзор" && efficiency.status === "ready" && <section><h3>Что делать дальше</h3>{efficiency.data.recommendations.map((item) => <details key={item.title} className="analytics-metric-group"><summary>{item.title}</summary><p>{item.reason}</p><p>{item.action}</p><small>Рекомендация · {item.priority === "high" ? "высокий приоритет" : "плановое улучшение"}</small></details>)}</section>}
      {analytics.status === "ready" && tab !== "Обзор" && <section><h3>{tab === "Отчёты" ? "Выгрузки по разделам" : "Открыть записи"}</h3><div className="analytics-actions">{(Object.keys(SECTION_META) as AnalyticsDetailSection[]).filter((key) => tab === "Отчёты" || (tab === "Люди" ? key === "users" : tab === "Деятельность" ? ["events","projects"].includes(key) : tab === "Возможности" ? key === "contacts" : key === "goals")).map((key) => <button key={key} onClick={() => setSelectedSection(key)}>{key === "users" ? "Все профили в базе" : SECTION_META[key].label} · {analytics.data[SECTION_META[key].value]} →</button>)}</div></section>}
      {tab === "Отчёты" && <section><h3>Журнал моих отчётов</h3><p>PDF и Excel формируются кнопками над вкладками с выбранными датами. В журнале — факт генерации, не прочтения файла.</p>{reports.status === "ready" && (reports.data.items.length ? <ul>{reports.data.items.map((item, i) => <li key={i}>{dateLabel(item.generated_at)} · {item.format.toUpperCase()} · {item.start}–{item.end}</li>)}</ul> : <p>Отчётов, сформированных после обновления, пока нет.</p>)}</section>}
    </section>
  </div>;
}
