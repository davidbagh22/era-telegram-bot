import { useCallback, useEffect, useMemo, useState } from "react";
import {
  createCareerItem,
  deleteCareerItem,
  downloadCareerResume,
  downloadOfficialRecommendation,
  fetchCareerDashboard,
  requestOfficialRecommendation,
  submitCareerVerification,
  updateCareerItem,
  updateCareerProfile,
  uploadCareerEvidence,
} from "../api/career";
import { ActionCell } from "../components/ActionCell";
import { BottomSheet } from "../components/BottomSheet";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { SkeletonCard } from "../components/Skeleton";
import { StatusBanner } from "../components/StatusBanner";
import { useToast } from "../components/Toast";
import type {
  CareerDashboard,
  CareerItemPayload,
  CareerPortfolioItem,
  CareerPurpose,
} from "../types/career";

const ITEM_TYPES: Array<{ value: string; label: string }> = [
  { value: "education", label: "Образование" },
  { value: "work", label: "Опыт работы" },
  { value: "internship", label: "Стажировка" },
  { value: "project", label: "Личный проект" },
  { value: "achievement", label: "Достижение / конкурс" },
  { value: "award", label: "Награда" },
  { value: "certificate", label: "Сертификат" },
  { value: "course", label: "Курс" },
  { value: "publication", label: "Публикация" },
  { value: "speech", label: "Выступление" },
  { value: "volunteer", label: "Волонтёрство вне ЭРА" },
  { value: "other", label: "Другое" },
];

const PURPOSES: Array<{ value: CareerPurpose; label: string; description: string }> = [
  { value: "universal", label: "Универсальное", description: "Сбалансированная версия" },
  { value: "work", label: "Работа", description: "Опыт → проекты → навыки" },
  { value: "internship", label: "Стажировка", description: "Образование → проекты → практика" },
  { value: "university", label: "Университет", description: "Образование → достижения → проекты" },
  { value: "grant", label: "Грант / конкурс", description: "Результаты → влияние → лидерство" },
  { value: "volunteer", label: "Волонтёрская программа", description: "Социальный вклад → проекты" },
];

const STATUS_META: Record<string, { label: string; mark: string }> = {
  self_reported: { label: "Добавлено участником", mark: "•" },
  pending: { label: "На проверке", mark: "◌" },
  verified: { label: "Подтверждено ЭРА", mark: "✓" },
  rejected: { label: "Нужно уточнить", mark: "!" },
};

const EMPTY_FORM: CareerItemPayload = {
  item_type: "achievement",
  title: "",
  organization: "",
  description: "",
  issued_at: null,
  url: "",
  include_in_resume: true,
};

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function Counter({ value, label }: { value: number; label: string }) {
  return (
    <Card style={{ padding: "0.9rem", minWidth: 0 }}>
      <strong style={{ display: "block", fontSize: "var(--era-text-2xl)" }}>{value}</strong>
      <span style={{ color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{label}</span>
    </Card>
  );
}

function ItemCard({
  item,
  busy,
  onUpload,
  onVerify,
  onToggleResume,
  onDelete,
}: {
  item: CareerPortfolioItem;
  busy: boolean;
  onUpload: (file: File) => void;
  onVerify: () => void;
  onToggleResume: () => void;
  onDelete: () => void;
}) {
  const status = STATUS_META[item.status] ?? STATUS_META.self_reported;
  const canEdit = item.status !== "verified";
  const canVerify = canEdit && item.status !== "pending" && (item.has_file || Boolean(item.url));
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem", alignItems: "flex-start" }}>
        <div style={{ minWidth: 0 }}>
          <strong style={{ overflowWrap: "anywhere" }}>{item.title}</strong>
          {(item.organization || item.issued_at) && (
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-sm)" }}>
              {[item.organization, item.issued_at].filter(Boolean).join(" · ")}
            </p>
          )}
        </div>
        <span style={{ whiteSpace: "nowrap", fontSize: "var(--era-text-xs)", fontWeight: 800, color: item.status === "verified" ? "var(--era-success)" : "var(--era-text-muted)" }}>
          {status.mark} {status.label}
        </span>
      </div>
      {item.description && <p style={{ margin: "0.75rem 0 0", color: "var(--era-text-muted)" }}>{item.description}</p>}
      {item.admin_comment && (
        <p style={{ margin: "0.65rem 0 0", fontSize: "var(--era-text-sm)" }}>Комментарий ЭРА: {item.admin_comment}</p>
      )}
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.8rem" }}>
        {item.has_file && <span style={{ fontSize: "var(--era-text-xs)", color: "var(--era-text-muted)" }}>📎 {item.file_name || "Документ"}</span>}
        {item.url && <a href={item.url} target="_blank" rel="noreferrer" style={{ fontSize: "var(--era-text-xs)" }}>Открыть ссылку ↗</a>}
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem", marginTop: "0.9rem" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.55rem", fontSize: "var(--era-text-sm)" }}>
          <input type="checkbox" checked={item.include_in_resume} disabled={!canEdit || busy} onChange={onToggleResume} />
          Добавлять в резюме
        </label>
        {canEdit && (
          <label style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", minHeight: 40, border: "1px solid var(--era-border)", borderRadius: "var(--era-radius-control)", cursor: busy ? "default" : "pointer", opacity: busy ? 0.6 : 1 }}>
            {item.has_file ? "Заменить подтверждение" : "Прикрепить подтверждение"}
            <input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx"
              disabled={busy}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) onUpload(file);
                event.currentTarget.value = "";
              }}
              style={{ display: "none" }}
            />
          </label>
        )}
        {canVerify && (
          <button type="button" className="era-btn-primary" disabled={busy} onClick={onVerify}>Отправить на подтверждение ЭРА</button>
        )}
        {item.status === "pending" && (
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>Редактирование вернёт запись из проверки. Дождитесь решения или обновите данные.</p>
        )}
        {canEdit && item.status !== "pending" && (
          <button type="button" disabled={busy} onClick={onDelete} style={{ color: "var(--era-error)" }}>Удалить запись</button>
        )}
      </div>
    </Card>
  );
}

export function CareerPortfolioScreen({ onBack }: { onBack: () => void }) {
  const [data, setData] = useState<CareerDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [form, setForm] = useState<CareerItemPayload>(EMPTY_FORM);
  const [profileDraft, setProfileDraft] = useState({ headline: "", about: "", languages: "" });
  const [purpose, setPurpose] = useState<CareerPurpose>("universal");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const toast = useToast();

  const refresh = useCallback(async () => {
    try {
      const next = await fetchCareerDashboard();
      setData(next);
      setProfileDraft({
        headline: next.profile.headline,
        about: next.profile.about,
        languages: next.profile.languages.map((item) => `${item.name}${item.level ? ` — ${item.level}` : ""}`).join("\n"),
      });
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const grouped = useMemo(() => {
    const result = new Map<string, CareerPortfolioItem[]>();
    for (const item of data?.items ?? []) {
      const label = ITEM_TYPES.find((option) => option.value === item.item_type)?.label ?? "Другое";
      result.set(label, [...(result.get(label) ?? []), item]);
    }
    return [...result.entries()];
  }, [data?.items]);

  const createItem = async () => {
    if (!form.title.trim()) {
      toast.show("Добавьте название результата", "error");
      return;
    }
    setSaving(true);
    try {
      await createCareerItem(form);
      setForm(EMPTY_FORM);
      setAddOpen(false);
      await refresh();
      toast.show("Добавлено в портфолио", "success");
    } catch {
      toast.show("Не удалось добавить запись", "error");
    } finally {
      setSaving(false);
    }
  };

  const saveProfile = async () => {
    setSaving(true);
    try {
      const languages = profileDraft.languages
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line) => {
          const [name, ...rest] = line.split("—");
          return { name: name.trim(), level: rest.join("—").trim() };
        });
      await updateCareerProfile({ headline: profileDraft.headline, about: profileDraft.about, languages });
      setProfileOpen(false);
      await refresh();
      toast.show("Профессиональный профиль обновлён", "success");
    } catch {
      toast.show("Не удалось сохранить профиль", "error");
    } finally {
      setSaving(false);
    }
  };

  const actOnItem = async (itemId: number, action: () => Promise<unknown>, success: string) => {
    setBusyId(itemId);
    try {
      await action();
      await refresh();
      toast.show(success, "success");
    } catch (err) {
      const message = err instanceof Error && err.message === "evidence_required"
        ? "Сначала прикрепите файл или ссылку"
        : "Не удалось выполнить действие";
      toast.show(message, "error");
    } finally {
      setBusyId(null);
    }
  };

  const downloadResume = async () => {
    setDownloading(true);
    try {
      saveBlob(await downloadCareerResume(purpose), `ERA_CV_${purpose}.pdf`);
      toast.show("Резюме готово", "success");
    } catch {
      toast.show("Не удалось сформировать резюме", "error");
    } finally {
      setDownloading(false);
    }
  };

  const requestRecommendation = async () => {
    setSaving(true);
    try {
      await requestOfficialRecommendation(purpose);
      await refresh();
      toast.show("Запрос отправлен на утверждение", "success");
    } catch {
      toast.show("Не удалось отправить запрос", "error");
    } finally {
      setSaving(false);
    }
  };

  const downloadRecommendation = async () => {
    const recommendation = data?.official_recommendation;
    if (!recommendation?.can_download) return;
    setDownloading(true);
    try {
      saveBlob(await downloadOfficialRecommendation(recommendation.id), `${recommendation.document_number ?? "ERA_recommendation"}.pdf`);
    } catch {
      toast.show("Не удалось скачать рекомендацию", "error");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return <div className="era-page" style={{ padding: "1.25rem", display: "grid", gap: "1rem" }}><SkeletonCard /><SkeletonCard /><SkeletonCard /></div>;
  }
  if (error || !data) {
    return <div className="era-page" style={{ padding: "1.25rem" }}><button type="button" onClick={onBack}>← Назад</button><StatusBanner title="Не удалось открыть портфолио" description="Обновите страницу и попробуйте снова." /></div>;
  }

  return (
    <div className="era-page era-stagger" style={{ padding: "1.25rem", display: "flex", flexDirection: "column", gap: "1rem", minWidth: 0 }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>← Профиль</button>

      <Card gradient>
        <p style={{ margin: "0 0 0.3rem", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)", fontWeight: 800, textTransform: "uppercase" }}>Профессиональный профиль</p>
        <h1 style={{ margin: 0, fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-2xl)" }}>Моё портфолио</h1>
        <p style={{ margin: "0.5rem 0 0", color: "var(--era-text-muted)" }}>Всё, что ты сделал. Всё, что можешь показать.</p>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.7rem" }}>
        <Counter value={data.counts.confirmed} label="подтверждено" />
        <Counter value={data.counts.added_by_me} label="добавлено мной" />
        <Counter value={data.counts.pending} label="на проверке" />
        <Counter value={data.counts.evidence_files} label="файлов" />
      </div>

      <button type="button" className="era-btn-primary" onClick={() => setAddOpen(true)}>＋ Добавить результат</button>
      <ActionCell title="Профессиональный профиль" description={data.profile.headline || "Добавьте позиционирование, кратко о себе и языки"} meta="Редактировать" onClick={() => setProfileOpen(true)} />

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Мои результаты</h2>
        {grouped.length === 0 ? (
          <EmptyState text="Пока здесь только автоматически подтверждённые результаты ЭРА. Добавьте образование, достижения, сертификаты или опыт вне организации." />
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {grouped.map(([label, items]) => (
              <div key={label}>
                <h3 style={{ margin: "0 0 0.55rem", fontSize: "var(--era-text-md)" }}>{label}</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.7rem" }}>
                  {items.map((item) => (
                    <ItemCard
                      key={item.id}
                      item={item}
                      busy={busyId === item.id}
                      onUpload={(file) => void actOnItem(item.id, () => uploadCareerEvidence(item.id, file), "Подтверждение прикреплено")}
                      onVerify={() => void actOnItem(item.id, () => submitCareerVerification(item.id), "Отправлено на проверку")}
                      onToggleResume={() => void actOnItem(item.id, () => updateCareerItem(item.id, { include_in_resume: !item.include_in_resume }), "Настройка резюме обновлена")}
                      onDelete={() => void actOnItem(item.id, () => deleteCareerItem(item.id), "Запись удалена")}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 style={{ margin: "0 0 0.75rem", fontSize: "var(--era-text-xl)" }}>Документы</h2>
        <Card>
          <strong>Резюме</strong>
          <p style={{ margin: "0.35rem 0 0.75rem", color: "var(--era-text-muted)" }}>Система перестроит акценты под цель. Внешнее резюме не показывает внутренние баллы ЭРА.</p>
          <select value={purpose} onChange={(event) => setPurpose(event.target.value as CareerPurpose)} style={{ width: "100%", minHeight: 44, marginBottom: "0.7rem" }}>
            {PURPOSES.map((item) => <option key={item.value} value={item.value}>{item.label} — {item.description}</option>)}
          </select>
          <button type="button" className="era-btn-primary" disabled={downloading} onClick={() => void downloadResume()} style={{ width: "100%" }}>
            {downloading ? "Формируем…" : "Собрать резюме PDF"}
          </button>
        </Card>

        <Card style={{ marginTop: "0.75rem" }}>
          <strong>Рекомендация ЭРА</strong>
          <p style={{ margin: "0.5rem 0", color: "var(--era-text-muted)" }}>{data.automatic_recommendation.text}</p>
          <p style={{ margin: "0.6rem 0 0", color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>{data.automatic_recommendation.privacy_note}</p>
          <div style={{ marginTop: "0.8rem", paddingTop: "0.8rem", borderTop: "1px solid var(--era-border)" }}>
            {!data.official_recommendation && (
              <button type="button" disabled={saving} onClick={() => void requestRecommendation()}>Запросить официальное письмо</button>
            )}
            {data.official_recommendation?.status === "requested" && <p style={{ margin: 0 }}>◌ Официальное письмо на утверждении</p>}
            {data.official_recommendation?.status === "rejected" && (
              <div>
                <p style={{ margin: "0 0 0.6rem" }}>Нужно уточнить запрос: {data.official_recommendation.rejection_comment || "без комментария"}</p>
                <button type="button" disabled={saving} onClick={() => void requestRecommendation()}>Отправить новый запрос</button>
              </div>
            )}
            {data.official_recommendation?.status === "approved" && (
              <button type="button" className="era-btn-primary" disabled={downloading} onClick={() => void downloadRecommendation()}>
                Скачать официальное письмо · {data.official_recommendation.document_number}
              </button>
            )}
          </div>
        </Card>
      </section>

      <BottomSheet open={addOpen} onClose={() => setAddOpen(false)} title="Добавить в портфолио">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <select value={form.item_type} onChange={(event) => setForm((prev) => ({ ...prev, item_type: event.target.value }))} style={{ minHeight: 44 }}>
            {ITEM_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <input placeholder="Название *" value={form.title} onChange={(event) => setForm((prev) => ({ ...prev, title: event.target.value }))} />
          <input placeholder="Организация" value={form.organization ?? ""} onChange={(event) => setForm((prev) => ({ ...prev, organization: event.target.value }))} />
          <textarea placeholder="За что / что именно сделал / какой результат" rows={4} value={form.description ?? ""} onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))} />
          <input type="date" value={form.issued_at ?? ""} onChange={(event) => setForm((prev) => ({ ...prev, issued_at: event.target.value || null }))} />
          <input placeholder="Ссылка на подтверждение или результат" value={form.url ?? ""} onChange={(event) => setForm((prev) => ({ ...prev, url: event.target.value }))} />
          <label style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}><input type="checkbox" checked={form.include_in_resume ?? true} onChange={(event) => setForm((prev) => ({ ...prev, include_in_resume: event.target.checked }))} />Добавлять в резюме</label>
          <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void createItem()}>{saving ? "Сохраняем…" : "Добавить"}</button>
          <p style={{ margin: 0, color: "var(--era-text-muted)", fontSize: "var(--era-text-xs)" }}>После создания можно прикрепить PDF, фото или документ и отправить запись на подтверждение ЭРА.</p>
        </div>
      </BottomSheet>

      <BottomSheet open={profileOpen} onClose={() => setProfileOpen(false)} title="Профессиональный профиль">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <input placeholder="Кто ты / профессиональное позиционирование" value={profileDraft.headline} onChange={(event) => setProfileDraft((prev) => ({ ...prev, headline: event.target.value }))} />
          <textarea rows={5} placeholder="О себе — 3–5 сильных предложений" value={profileDraft.about} onChange={(event) => setProfileDraft((prev) => ({ ...prev, about: event.target.value }))} />
          <textarea rows={4} placeholder={"Языки — по одному на строку\nРусский — C2\nАнглийский — B2"} value={profileDraft.languages} onChange={(event) => setProfileDraft((prev) => ({ ...prev, languages: event.target.value }))} />
          <button type="button" className="era-btn-primary" disabled={saving} onClick={() => void saveProfile()}>{saving ? "Сохраняем…" : "Сохранить"}</button>
        </div>
      </BottomSheet>
    </div>
  );
}
