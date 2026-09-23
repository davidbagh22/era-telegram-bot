import { useCallback, useEffect, useMemo, useState } from "react";
import {
  assignOffice,
  createOffice,
  deleteOffice,
  describeActionError,
  removeOfficeAssignment,
  searchAssignableUsers,
} from "../../api/client";
import {
  appointRoleApplication,
  decideRoleApplication,
  fetchRecruitmentOffices,
  fetchRoleApplication,
  fetchRoleApplications,
  updateRecruitmentOffice,
  type PositionApplicationAdmin,
  type RecruitmentOffice,
} from "../../api/recruitment";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import { useAsync } from "../../hooks/useAsync";
import type { UserListItem } from "../../types/admin";

const inputStyle = {
  width: "100%",
  fontFamily: "var(--era-font-body)",
  padding: "0.65rem",
  minHeight: 44,
  borderRadius: "0.65rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
} as const;

const STATUS_LABELS: Record<string, string> = {
  submitted: "Новая",
  reviewing: "На рассмотрении",
  needs_info: "Нужна информация",
  interview: "Интервью",
  reserve: "Резерв",
  approved: "Одобрена",
  rejected: "Отклонена",
  withdrawn: "Отозвана",
  appointed: "Назначен",
};

function ApplicationCard({
  application,
  onChanged,
}: {
  application: PositionApplicationAdmin;
  onChanged: (value: PositionApplicationAdmin) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(application.review_note ?? "");
  const [error, setError] = useState<string | null>(null);

  async function decide(status: "reviewing" | "needs_info" | "interview" | "reserve" | "approved" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      onChanged(await decideRoleApplication(application.id, status, note));
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setBusy(false);
    }
  }

  async function appoint() {
    setBusy(true);
    setError(null);
    try {
      onChanged(await appointRoleApplication(application.id));
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card style={{ padding: "1rem" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: ".7rem", alignItems: "flex-start" }}>
        <div>
          <strong style={{ fontSize: "1.05rem" }}>{application.user_name}</strong>
          <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-muted)", fontSize: ".8rem" }}>
            {application.facts.participation_label} · {STATUS_LABELS[application.status] ?? application.status}
          </span>
        </div>
        <MonoLabel tone="violet">#{application.id}</MonoLabel>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".5rem", marginTop: ".8rem" }}>
        <Fact title="Проекты" value={application.facts.completed_projects} />
        <Fact title="События" value={application.facts.events_attended} />
        <Fact title="Задачи" value={application.facts.tasks_completed_total} />
        <Fact title="В срок" value={application.facts.on_time_rate == null ? "—" : `${application.facts.on_time_rate}%`} />
        <Fact title="Портфолио" value={application.facts.portfolio_items} />
        <Fact title="Баллы" value={application.facts.points} />
      </div>

      {application.facts.current_offices.length > 0 && (
        <p style={{ margin: ".8rem 0 0", color: "var(--era-text-secondary)", fontSize: ".82rem" }}>
          Текущие роли: {application.facts.current_offices.join(", ")}
        </p>
      )}
      <TextBlock title="Почему хочет роль" value={application.motivation} />
      <TextBlock title="Релевантный опыт" value={application.relevant_experience} />
      <TextBlock title="План на 1–2 месяца" value={application.plan} />
      <TextBlock title="Доступность" value={application.availability} />
      {application.attachment_url && (
        <a href={application.attachment_url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginTop: ".7rem" }}>
          Дополнительная ссылка ↗
        </a>
      )}

      <textarea
        rows={2}
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Комментарий кандидату"
        style={{ ...inputStyle, marginTop: ".8rem" }}
      />
      {error && <p style={{ color: "var(--era-error)", fontSize: ".8rem" }}>{error}</p>}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2,minmax(0,1fr))", gap: ".45rem", marginTop: ".65rem" }}>
        <button type="button" disabled={busy} onClick={() => void decide("reviewing")}>Рассматриваем</button>
        <button type="button" disabled={busy} onClick={() => void decide("needs_info")}>Уточнить</button>
        <button type="button" disabled={busy} onClick={() => void decide("interview")}>Интервью</button>
        <button type="button" disabled={busy} onClick={() => void decide("reserve")}>В резерв</button>
        <button type="button" disabled={busy} onClick={() => void decide("approved")}>Одобрить</button>
        <button type="button" disabled={busy} onClick={() => void decide("rejected")}>Отклонить</button>
      </div>
      {application.status === "approved" && (
        <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void appoint()} style={{ width: "100%", marginTop: ".55rem" }}>
          Назначить на должность
        </button>
      )}
    </Card>
  );
}

function Fact({ title, value }: { title: string; value: string | number }) {
  return <div style={{ padding: ".55rem", borderRadius: ".65rem", background: "var(--era-surface-2)" }}><strong>{value}</strong><span style={{ display: "block", color: "var(--era-text-muted)", fontSize: ".72rem" }}>{title}</span></div>;
}

function TextBlock({ title, value }: { title: string; value: string | null }) {
  if (!value) return null;
  return <div style={{ marginTop: ".7rem" }}><MonoLabel>{title}</MonoLabel><p style={{ margin: ".25rem 0 0", color: "var(--era-text-secondary)", whiteSpace: "pre-wrap", lineHeight: 1.45 }}>{value}</p></div>;
}

function OfficeSettings({ office, onSaved }: { office: RecruitmentOffice; onSaved: () => void }) {
  const [mode, setMode] = useState(office.recruitment_mode);
  const [capacity, setCapacity] = useState(office.capacity == null ? "" : String(office.capacity));
  const [manualOpen, setManualOpen] = useState(office.application_enabled);
  const [responsibilities, setResponsibilities] = useState(office.responsibilities.join("\n"));
  const [requirements, setRequirements] = useState(office.requirements ?? "");
  const [expectedResult, setExpectedResult] = useState(office.expected_result ?? "");
  const [workload, setWorkload] = useState(office.workload ?? "");
  const [deadline, setDeadline] = useState(office.application_deadline?.slice(0, 16) ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await updateRecruitmentOffice(office.id, {
        recruitment_mode: mode,
        capacity: capacity.trim() ? Number(capacity) : null,
        application_enabled: mode === "manual" ? manualOpen : null,
        responsibilities: responsibilities.split("\n").map((item) => item.trim()).filter(Boolean),
        requirements: requirements.trim() || null,
        expected_result: expectedResult.trim() || null,
        workload: workload.trim() || null,
        application_deadline: deadline ? new Date(deadline).toISOString() : null,
        is_public: true,
      });
      onSaved();
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: ".5rem", marginTop: ".8rem" }}>
      <select value={mode} onChange={(event) => setMode(event.target.value as RecruitmentOffice["recruitment_mode"])} style={inputStyle}>
        <option value="auto">Авто — открывать при свободном месте</option>
        <option value="manual">Вручную</option>
        <option value="closed">Набор закрыт</option>
      </select>
      <input type="number" min={1} value={capacity} onChange={(event) => setCapacity(event.target.value)} placeholder="Количество мест (пусто = без лимита)" style={inputStyle} />
      {mode === "manual" && <label style={{ display: "flex", gap: ".55rem", alignItems: "center", minHeight: 44 }}><input type="checkbox" checked={manualOpen} onChange={(event) => setManualOpen(event.target.checked)} />Приём заявок открыт</label>}
      <textarea rows={3} value={responsibilities} onChange={(event) => setResponsibilities(event.target.value)} placeholder="Ответственности — по одной на строку" style={inputStyle} />
      <textarea rows={2} value={requirements} onChange={(event) => setRequirements(event.target.value)} placeholder="Требования" style={inputStyle} />
      <textarea rows={2} value={expectedResult} onChange={(event) => setExpectedResult(event.target.value)} placeholder="Ожидаемый результат" style={inputStyle} />
      <input value={workload} onChange={(event) => setWorkload(event.target.value)} placeholder="Нагрузка, например 3–5 часов в неделю" style={inputStyle} />
      <input type="datetime-local" value={deadline} onChange={(event) => setDeadline(event.target.value)} style={inputStyle} />
      {error && <p style={{ color: "var(--era-error)", fontSize: ".8rem", margin: 0 }}>{error}</p>}
      <button type="button" className="era-btn-primary" disabled={busy} onClick={() => void save()}>{busy ? "Сохраняем…" : "Сохранить настройки"}</button>
    </div>
  );
}

export function AdminOfficesScreen() {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchRecruitmentOffices(), [refreshKey]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [assigningOfficeId, setAssigningOfficeId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<UserListItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [expandedOfficeId, setExpandedOfficeId] = useState<number | null>(null);
  const [applications, setApplications] = useState<PositionApplicationAdmin[]>([]);
  const [applicationsLoading, setApplicationsLoading] = useState(false);
  const [deepLinkedApplication, setDeepLinkedApplication] = useState<PositionApplicationAdmin | null>(null);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);
  const deepLinkedId = useMemo(() => Number(new URLSearchParams(window.location.search).get("positionApplicationId") || 0), []);

  useEffect(() => {
    if (!deepLinkedId) return;
    void fetchRoleApplication(deepLinkedId)
      .then((application) => {
        setDeepLinkedApplication(application);
        setExpandedOfficeId(application.office_id);
      })
      .catch(() => setActionError("Не удалось открыть заявку по ссылке."));
  }, [deepLinkedId]);

  useEffect(() => {
    if (!expandedOfficeId) {
      setApplications([]);
      return;
    }
    setApplicationsLoading(true);
    void fetchRoleApplications(expandedOfficeId)
      .then(setApplications)
      .catch((error) => setActionError(describeActionError(error)))
      .finally(() => setApplicationsLoading(false));
  }, [expandedOfficeId, refreshKey]);

  const handleCreate = useCallback(async () => {
    if (!title.trim()) return;
    setCreating(true);
    setActionError(null);
    try {
      await createOffice(title.trim(), description.trim());
      setTitle("");
      setDescription("");
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setCreating(false);
    }
  }, [title, description, refresh]);

  const runAction = useCallback(async (officeId: number, action: () => Promise<unknown>) => {
    setBusyId(officeId);
    setActionError(null);
    try {
      await action();
      refresh();
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setBusyId(null);
    }
  }, [refresh]);

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    setActionError(null);
    try {
      setCandidates(await searchAssignableUsers(query.trim()));
    } catch (error) {
      setActionError(describeActionError(error));
    } finally {
      setSearching(false);
    }
  }

  function updateApplication(value: PositionApplicationAdmin) {
    setApplications((items) => items.map((item) => item.id === value.id ? value : item));
    if (deepLinkedApplication?.id === value.id) setDeepLinkedApplication(value);
    refresh();
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.8rem" }}>
      {actionError && <p style={{ color: "var(--era-error)", fontSize: ".82rem", margin: 0 }}>{actionError}</p>}
      {deepLinkedApplication && (
        <section style={{ display: "flex", flexDirection: "column", gap: ".5rem" }}>
          <MonoLabel tone="violet">Заявка из уведомления</MonoLabel>
          <ApplicationCard application={deepLinkedApplication} onChanged={updateApplication} />
        </section>
      )}

      <Card>
        <strong>Новая должность</strong>
        <div style={{ display: "flex", flexDirection: "column", gap: ".5rem", marginTop: ".5rem" }}>
          <input placeholder="Название" value={title} onChange={(event) => setTitle(event.target.value)} style={inputStyle} />
          <textarea placeholder="Коротко о роли" value={description} onChange={(event) => setDescription(event.target.value)} rows={2} style={inputStyle} />
          <button type="button" className="era-btn-primary" disabled={creating || !title.trim()} onClick={() => void handleCreate()}>{creating ? "Добавляем…" : "Добавить должность"}</button>
        </div>
      </Card>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить должности." />}
      {state.status === "ready" && state.data.length === 0 && <EmptyState text="Должностей пока нет." />}
      {state.status === "ready" && state.data.map((office) => {
        const expanded = expandedOfficeId === office.id;
        return (
          <Card key={office.id}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: ".7rem", alignItems: "flex-start" }}>
              <div>
                <strong>{office.title}</strong>
                <span style={{ display: "block", marginTop: ".2rem", color: "var(--era-text-muted)", fontSize: ".78rem" }}>
                  {office.recruitment_mode === "auto" ? "Автонабор" : office.recruitment_mode === "manual" ? "Ручной набор" : "Набор закрыт"} · {office.occupied}{office.capacity == null ? "" : `/${office.capacity}`} занято · заявок {office.application_count}
                </span>
              </div>
              <button type="button" onClick={() => setExpandedOfficeId(expanded ? null : office.id)}>{expanded ? "Свернуть" : "Управлять"}</button>
            </div>
            {office.description && <p style={{ margin: ".45rem 0", color: "var(--era-text-secondary)" }}>{office.description}</p>}
            {expanded && (
              <div style={{ marginTop: ".8rem", display: "flex", flexDirection: "column", gap: ".8rem" }}>
                <OfficeSettings office={office} onSaved={refresh} />

                <section>
                  <MonoLabel>Назначения</MonoLabel>
                  {office.assignments.length === 0 ? <p style={{ color: "var(--era-text-muted)", fontSize: ".82rem" }}>Пока никто не назначен.</p> : office.assignments.map((assignment) => (
                    <div key={assignment.assignment_id} style={{ display: "flex", justifyContent: "space-between", gap: ".6rem", alignItems: "center", minHeight: 44 }}>
                      <span>{assignment.user_name}</span>
                      <button type="button" disabled={busyId === office.id} onClick={() => void runAction(office.id, () => removeOfficeAssignment(assignment.assignment_id))}>Завершить</button>
                    </div>
                  ))}
                  {assigningOfficeId === office.id ? (
                    <div style={{ display: "flex", flexDirection: "column", gap: ".45rem" }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: ".45rem" }}>
                        <input placeholder="Имя, username или Telegram ID" value={query} onChange={(event) => setQuery(event.target.value)} style={inputStyle} />
                        <button type="button" disabled={searching || !query.trim()} onClick={() => void handleSearch()}>Найти</button>
                      </div>
                      {candidates.map((candidate) => <button key={candidate.id} type="button" onClick={() => void runAction(office.id, async () => { await assignOffice(office.id, candidate.id); setAssigningOfficeId(null); })} style={{ textAlign: "left" }}>{candidate.first_name} {candidate.last_name ?? ""}</button>)}
                      <button type="button" onClick={() => setAssigningOfficeId(null)}>Отмена</button>
                    </div>
                  ) : <button type="button" onClick={() => { setAssigningOfficeId(office.id); setCandidates([]); setQuery(""); }}>Назначить человека</button>}
                </section>

                <section style={{ display: "flex", flexDirection: "column", gap: ".55rem" }}>
                  <MonoLabel>Заявки на роль</MonoLabel>
                  {applicationsLoading ? <p style={{ color: "var(--era-text-muted)" }}>Загрузка заявок…</p> : applications.length === 0 ? <EmptyState text="Заявок на эту роль пока нет." /> : applications.map((application) => <ApplicationCard key={application.id} application={application} onChanged={updateApplication} />)}
                </section>

                <button type="button" disabled={busyId === office.id} onClick={() => void runAction(office.id, () => deleteOffice(office.id))} style={{ color: "var(--era-error)" }}>Архивировать должность</button>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
