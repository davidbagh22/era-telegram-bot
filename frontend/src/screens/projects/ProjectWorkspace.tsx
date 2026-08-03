import { useCallback, useEffect, useMemo, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  addProjectMember,
  applyToProjectRole,
  approveProjectApplication,
  assignProjectTask,
  changeProjectMemberRole,
  confirmProjectContribution,
  createProjectMilestone,
  createProjectRole,
  createProjectTask,
  fetchProjectWorkspace,
  linkProjectEvent,
  messageProjectTeam,
  rejectProjectApplication,
  setProjectMilestoneStatus,
  setProjectRoleStatus,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MetricCard } from "../../components/MetricCard";
import { PillTabs } from "../../components/PillTabs";
import { ProgressBar } from "../../components/ProgressBar";
import { StatusBadge } from "../../components/StatusBadge";
import type { ProjectMember, ProjectRole, ProjectWorkspace as ProjectWorkspaceType } from "../../types/project";

type WorkspaceTab = "overview" | "team" | "tasks" | "milestones" | "events" | "materials" | "analytics";

const TABS: { value: WorkspaceTab; label: string }[] = [
  { value: "overview", label: "Обзор" },
  { value: "team", label: "Команда" },
  { value: "tasks", label: "Задачи" },
  { value: "milestones", label: "Этапы" },
  { value: "events", label: "События" },
  { value: "materials", label: "Материалы" },
  { value: "analytics", label: "Аналитика" },
];

const MEMBER_ACTIVE_STATUSES = new Set(["accepted", "active", "completed"]);

const inputStyle = {
  fontFamily: "var(--era-font-body)",
  minHeight: "2.75rem",
  padding: "0.625rem 0.75rem",
  borderRadius: "0.75rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

const buttonStyle = {
  minHeight: "2.75rem",
  border: "1px solid var(--era-red)",
  borderRadius: "0.875rem",
  background: "var(--era-red)",
  color: "#fff",
  fontFamily: "var(--era-font-body)",
  fontWeight: 700,
} satisfies CSSProperties;

const secondaryButtonStyle = {
  ...buttonStyle,
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} satisfies CSSProperties;

function formatDate(value: string | null): string {
  if (!value) return "Без срока";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function dateTimeLocalToIso(value: string): string | undefined {
  return value ? new Date(value).toISOString() : undefined;
}

function optionalNumber(value: string): number | undefined {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function memberLabel(member: ProjectMember): string {
  return `${member.full_name}${member.role_title ? ` · ${member.role_title}` : ""}`;
}

function roleFill(role: ProjectRole): string {
  return `${role.filled} / ${role.capacity ?? "∞"}`;
}

interface ProjectWorkspaceProps {
  projectId: number;
}

export function ProjectWorkspace({ projectId }: ProjectWorkspaceProps) {
  const [workspace, setWorkspace] = useState<ProjectWorkspaceType | null>(null);
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [roleTitle, setRoleTitle] = useState("");
  const [roleCapacity, setRoleCapacity] = useState("");
  const [applicationText, setApplicationText] = useState("");
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRoleId, setMemberRoleId] = useState("");
  const [milestoneTitle, setMilestoneTitle] = useState("");
  const [milestoneDeadline, setMilestoneDeadline] = useState("");
  const [milestoneResponsibleId, setMilestoneResponsibleId] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskDeadline, setTaskDeadline] = useState("");
  const [taskAssigneeId, setTaskAssigneeId] = useState("");
  const [taskPoints, setTaskPoints] = useState("10");
  const [eventId, setEventId] = useState("");
  const [contributionMemberId, setContributionMemberId] = useState("");
  const [contributionSummary, setContributionSummary] = useState("");
  const [contributionResult, setContributionResult] = useState("");
  const [teamMessage, setTeamMessage] = useState("");

  const loadWorkspace = useCallback(async () => {
    setError(null);
    try {
      setWorkspace(await fetchProjectWorkspace(projectId));
    } catch {
      setError("Не удалось загрузить рабочее пространство проекта.");
    }
  }, [projectId]);

  useEffect(() => {
    void loadWorkspace();
  }, [loadWorkspace]);

  const activeMembers = useMemo(
    () => workspace?.members.filter((member) => MEMBER_ACTIVE_STATUSES.has(member.status)) ?? [],
    [workspace],
  );
  const pendingMembers = useMemo(
    () => workspace?.members.filter((member) => member.status === "pending") ?? [],
    [workspace],
  );

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      await loadWorkspace();
    } catch {
      setError("Действие не выполнено. Проверьте данные и попробуйте ещё раз.");
    } finally {
      setBusy(false);
    }
  }

  if (error && !workspace) {
    return <EmptyState text={error} />;
  }
  if (!workspace) {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }

  const canApply = !workspace.can_manage && !workspace.viewer_membership_status;
  const completedTasks = workspace.tasks.filter((task) => task.status === "completed").length;
  const confirmedMembers = activeMembers.filter(
    (member) => member.contribution_status === "confirmed",
  ).length;
  const nextMilestone = workspace.milestones.find((item) => item.status !== "completed");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      {error && <EmptyState text={error} />}

      <Card>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
            <div>
              <div style={{ fontFamily: "var(--era-font-display)", fontSize: "1.125rem" }}>
                {workspace.project.title}
              </div>
              <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                {workspace.project.short_description}
              </p>
            </div>
            <StatusBadge label={workspace.project.status} tone="violet" />
          </div>
          <ProgressBar
            currentIndex={Math.round(workspace.progress_percent / 25)}
            totalSteps={5}
            labels={["0", "25", "50", "75", "100"]}
          />
        </div>
      </Card>

      <PillTabs options={TABS} active={activeTab} onChange={setActiveTab} />

      {activeTab === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
              gap: "0.75rem",
            }}
          >
            <MetricCard label="Команда" value={activeMembers.length} />
            <MetricCard label="Задачи" value={`${completedTasks}/${workspace.tasks.length}`} />
            <MetricCard label="Этапы" value={`${workspace.progress_percent}%`} />
            <MetricCard label="События" value={workspace.events.length} />
          </div>
          <Card>
            <SectionTitle title="Следующий этап" />
            {nextMilestone ? (
              <div>
                <strong>{nextMilestone.title}</strong>
                <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                  {formatDate(nextMilestone.deadline)}
                </p>
              </div>
            ) : (
              <EmptyState text="Активных этапов нет." />
            )}
          </Card>
          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Сообщение команде" />
              <FormStack>
                <textarea
                  value={teamMessage}
                  onChange={(event) => setTeamMessage(event.target.value)}
                  rows={3}
                  style={inputStyle}
                />
                <button
                  type="button"
                  disabled={busy || !teamMessage.trim()}
                  onClick={() =>
                    run(async () => {
                      await messageProjectTeam(projectId, teamMessage);
                      setTeamMessage("");
                    })
                  }
                  style={buttonStyle}
                >
                  Отправить
                </button>
              </FormStack>
            </Card>
          )}
        </div>
      )}

      {activeTab === "team" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Новая роль" />
              <FormStack>
                <input
                  value={roleTitle}
                  onChange={(event) => setRoleTitle(event.target.value)}
                  placeholder="Название роли"
                  style={inputStyle}
                />
                <input
                  value={roleCapacity}
                  onChange={(event) => setRoleCapacity(event.target.value)}
                  inputMode="numeric"
                  placeholder="Количество мест"
                  style={inputStyle}
                />
                <button
                  type="button"
                  disabled={busy || !roleTitle.trim()}
                  onClick={() =>
                    run(async () => {
                      await createProjectRole(projectId, {
                        title: roleTitle,
                        capacity: optionalNumber(roleCapacity),
                      });
                      setRoleTitle("");
                      setRoleCapacity("");
                    })
                  }
                  style={buttonStyle}
                >
                  Открыть роль
                </button>
              </FormStack>
            </Card>
          )}

          {workspace.roles.map((role) => (
            <Card key={role.id}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                <div>
                  <strong>{role.title}</strong>
                  <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)" }}>
                    {roleFill(role)}
                  </p>
                </div>
                <StatusBadge label={role.status} tone={role.status === "open" ? "violet" : "neutral"} />
              </div>
              {role.requirements && (
                <p style={{ color: "var(--era-text-muted)" }}>{role.requirements}</p>
              )}
              {workspace.can_manage ? (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(() =>
                      setProjectRoleStatus(projectId, role.id, role.status === "open" ? "closed" : "open"),
                    )
                  }
                  style={secondaryButtonStyle}
                >
                  {role.status === "open" ? "Закрыть набор" : "Открыть набор"}
                </button>
              ) : (
                canApply &&
                role.status === "open" && (
                  <FormStack>
                    <textarea
                      value={applicationText}
                      onChange={(event) => setApplicationText(event.target.value)}
                      rows={2}
                      style={inputStyle}
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          await applyToProjectRole(projectId, {
                            role_id: role.id,
                            text: applicationText,
                          });
                          setApplicationText("");
                        })
                      }
                      style={buttonStyle}
                    >
                      Подать заявку
                    </button>
                  </FormStack>
                )
              )}
            </Card>
          ))}

          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Заявки" />
              {pendingMembers.length === 0 ? (
                <EmptyState text="Новых заявок нет." />
              ) : (
                <ListStack>
                  {pendingMembers.map((member) => (
                    <div key={member.id} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      <strong>{memberLabel(member)}</strong>
                      {member.application_text && (
                        <p style={{ margin: 0, color: "var(--era-text-muted)" }}>
                          {member.application_text}
                        </p>
                      )}
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => run(() => approveProjectApplication(projectId, member.id))}
                          style={buttonStyle}
                        >
                          Принять
                        </button>
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => run(() => rejectProjectApplication(projectId, member.id))}
                          style={secondaryButtonStyle}
                        >
                          Отклонить
                        </button>
                      </div>
                    </div>
                  ))}
                </ListStack>
              )}
            </Card>
          )}

          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Добавить участника" />
              <FormStack>
                <input
                  value={memberUserId}
                  onChange={(event) => setMemberUserId(event.target.value)}
                  inputMode="numeric"
                  placeholder="ID участника"
                  style={inputStyle}
                />
                <RoleSelect value={memberRoleId} roles={workspace.roles} onChange={setMemberRoleId} />
                <button
                  type="button"
                  disabled={busy || !optionalNumber(memberUserId)}
                  onClick={() =>
                    run(async () => {
                      await addProjectMember(projectId, {
                        user_id: optionalNumber(memberUserId) ?? 0,
                        role_id: optionalNumber(memberRoleId),
                      });
                      setMemberUserId("");
                    })
                  }
                  style={buttonStyle}
                >
                  Добавить
                </button>
              </FormStack>
            </Card>
          )}

          <Card>
            <SectionTitle title="Участники" />
            {activeMembers.length === 0 ? (
              <EmptyState text="Команда пока не собрана." />
            ) : (
              <ListStack>
                {activeMembers.map((member) => (
                  <div key={member.id}>
                    <strong>{member.full_name}</strong>
                    <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
                      {member.role_title ?? "Роль не назначена"} · {member.contribution_status}
                    </p>
                    {workspace.can_manage && (
                      <RoleSelect
                        value={member.role_id?.toString() ?? ""}
                        roles={workspace.roles}
                        onChange={(value) =>
                          run(() => changeProjectMemberRole(projectId, member.id, optionalNumber(value)))
                        }
                      />
                    )}
                  </div>
                ))}
              </ListStack>
            )}
          </Card>

          {workspace.can_manage && activeMembers.length > 0 && (
            <Card>
              <SectionTitle title="Вклад" />
              <FormStack>
                <MemberSelect
                  value={contributionMemberId}
                  members={activeMembers}
                  onChange={setContributionMemberId}
                />
                <textarea
                  value={contributionSummary}
                  onChange={(event) => setContributionSummary(event.target.value)}
                  rows={2}
                  style={inputStyle}
                />
                <input
                  value={contributionResult}
                  onChange={(event) => setContributionResult(event.target.value)}
                  placeholder="Результат"
                  style={inputStyle}
                />
                <button
                  type="button"
                  disabled={busy || !optionalNumber(contributionMemberId) || !contributionSummary.trim()}
                  onClick={() =>
                    run(async () => {
                      await confirmProjectContribution(
                        projectId,
                        optionalNumber(contributionMemberId) ?? 0,
                        {
                          summary: contributionSummary,
                          result: contributionResult,
                        },
                      );
                      setContributionSummary("");
                      setContributionResult("");
                    })
                  }
                  style={buttonStyle}
                >
                  Подтвердить вклад
                </button>
              </FormStack>
            </Card>
          )}
        </div>
      )}

      {activeTab === "tasks" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Новая задача" />
              <FormStack>
                <input
                  value={taskTitle}
                  onChange={(event) => setTaskTitle(event.target.value)}
                  placeholder="Название"
                  style={inputStyle}
                />
                <textarea
                  value={taskDescription}
                  onChange={(event) => setTaskDescription(event.target.value)}
                  rows={2}
                  style={inputStyle}
                />
                <input
                  type="datetime-local"
                  value={taskDeadline}
                  onChange={(event) => setTaskDeadline(event.target.value)}
                  style={inputStyle}
                />
                <MemberSelect value={taskAssigneeId} members={activeMembers} onChange={setTaskAssigneeId} />
                <input
                  value={taskPoints}
                  onChange={(event) => setTaskPoints(event.target.value)}
                  inputMode="numeric"
                  placeholder="Баллы"
                  style={inputStyle}
                />
                <button
                  type="button"
                  disabled={busy || !taskTitle.trim() || !taskDescription.trim() || !taskDeadline}
                  onClick={() =>
                    run(async () => {
                      await createProjectTask(projectId, {
                        title: taskTitle,
                        description: taskDescription,
                        deadline: dateTimeLocalToIso(taskDeadline) ?? "",
                        assignee_id: optionalNumber(taskAssigneeId),
                        points: optionalNumber(taskPoints) ?? 10,
                      });
                      setTaskTitle("");
                      setTaskDescription("");
                      setTaskDeadline("");
                    })
                  }
                  style={buttonStyle}
                >
                  Создать задачу
                </button>
              </FormStack>
            </Card>
          )}
          {workspace.tasks.length === 0 ? (
            <EmptyState text="Задач пока нет." />
          ) : (
            workspace.tasks.map((task) => (
              <Card key={task.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <div>
                    <strong>{task.title}</strong>
                    <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
                      {formatDate(task.deadline)} · {task.points} баллов
                    </p>
                  </div>
                  <StatusBadge label={task.status} tone="violet" />
                </div>
                {workspace.can_manage && (
                  <MemberSelect
                    value={task.assignee_id?.toString() ?? ""}
                    members={activeMembers}
                    onChange={(value) => run(() => assignProjectTask(projectId, task.id, optionalNumber(value)))}
                  />
                )}
              </Card>
            ))
          )}
        </div>
      )}

      {activeTab === "milestones" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Новый этап" />
              <FormStack>
                <input
                  value={milestoneTitle}
                  onChange={(event) => setMilestoneTitle(event.target.value)}
                  placeholder="Название"
                  style={inputStyle}
                />
                <input
                  type="datetime-local"
                  value={milestoneDeadline}
                  onChange={(event) => setMilestoneDeadline(event.target.value)}
                  style={inputStyle}
                />
                <MemberSelect
                  value={milestoneResponsibleId}
                  members={activeMembers}
                  onChange={setMilestoneResponsibleId}
                />
                <button
                  type="button"
                  disabled={busy || !milestoneTitle.trim()}
                  onClick={() =>
                    run(async () => {
                      await createProjectMilestone(projectId, {
                        title: milestoneTitle,
                        deadline: dateTimeLocalToIso(milestoneDeadline),
                        responsible_id: optionalNumber(milestoneResponsibleId),
                      });
                      setMilestoneTitle("");
                      setMilestoneDeadline("");
                    })
                  }
                  style={buttonStyle}
                >
                  Создать этап
                </button>
              </FormStack>
            </Card>
          )}
          {workspace.milestones.length === 0 ? (
            <EmptyState text="Этапов пока нет." />
          ) : (
            <div style={{ borderLeft: "2px solid var(--era-border)", paddingLeft: "0.75rem" }}>
              {workspace.milestones.map((milestone) => (
                <Card key={milestone.id} style={{ marginBottom: "0.75rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                    <div>
                      <strong>{milestone.title}</strong>
                      <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
                        {formatDate(milestone.deadline)}
                      </p>
                    </div>
                    <StatusBadge
                      label={milestone.status}
                      tone={milestone.status === "completed" ? "neutral" : "violet"}
                    />
                  </div>
                  {workspace.can_manage && milestone.status !== "completed" && (
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        run(() => setProjectMilestoneStatus(projectId, milestone.id, "completed"))
                      }
                      style={secondaryButtonStyle}
                    >
                      Завершить этап
                    </button>
                  )}
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "events" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {workspace.can_manage && (
            <Card>
              <SectionTitle title="Связать событие" />
              <FormStack>
                <input
                  value={eventId}
                  onChange={(event) => setEventId(event.target.value)}
                  inputMode="numeric"
                  placeholder="ID события"
                  style={inputStyle}
                />
                <button
                  type="button"
                  disabled={busy || !optionalNumber(eventId)}
                  onClick={() =>
                    run(async () => {
                      await linkProjectEvent(projectId, optionalNumber(eventId) ?? 0);
                      setEventId("");
                    })
                  }
                  style={buttonStyle}
                >
                  Связать
                </button>
              </FormStack>
            </Card>
          )}
          {workspace.events.length === 0 ? (
            <EmptyState text="Связанных событий пока нет." />
          ) : (
            workspace.events.map((event) => (
              <Card key={event.id}>
                <div style={{ display: "flex", justifyContent: "space-between", gap: "0.75rem" }}>
                  <div>
                    <strong>{event.title}</strong>
                    <p style={{ margin: "0.25rem 0", color: "var(--era-text-muted)" }}>
                      {event.event_date} · {event.event_time}
                    </p>
                  </div>
                  <StatusBadge label={event.status} tone="violet" />
                </div>
              </Card>
            ))
          )}
        </div>
      )}

      {activeTab === "materials" && <EmptyState text="Материалов пока нет." />}

      {activeTab === "analytics" && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
            gap: "0.75rem",
          }}
        >
          <MetricCard label="Прогресс" value={`${workspace.progress_percent}%`} />
          <MetricCard label="Подтверждён вклад" value={`${confirmedMembers}/${activeMembers.length}`} />
          <MetricCard label="Задачи выполнены" value={`${completedTasks}/${workspace.tasks.length}`} />
          <MetricCard label="Роли открыты" value={workspace.roles.filter((role) => role.status === "open").length} />
        </div>
      )}
    </div>
  );
}

function SectionTitle({ title }: { title: string }) {
  return (
    <h2
      style={{
        margin: "0 0 0.75rem",
        fontFamily: "var(--era-font-display)",
        fontSize: "1rem",
      }}
    >
      {title}
    </h2>
  );
}

function FormStack({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>{children}</div>;
}

function ListStack({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>{children}</div>;
}

function RoleSelect({
  value,
  roles,
  onChange,
}: {
  value: string;
  roles: ProjectRole[];
  onChange: (value: string) => void;
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} style={inputStyle}>
      <option value="">Без роли</option>
      {roles.map((role) => (
        <option key={role.id} value={role.id}>
          {role.title}
        </option>
      ))}
    </select>
  );
}

function MemberSelect({
  value,
  members,
  onChange,
}: {
  value: string;
  members: ProjectMember[];
  onChange: (value: string) => void;
}) {
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} style={inputStyle}>
      <option value="">Не назначен</option>
      {members.map((member) => (
        <option key={member.user_id} value={member.user_id}>
          {memberLabel(member)}
        </option>
      ))}
    </select>
  );
}
