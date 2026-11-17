import { useCallback, useEffect, useMemo, useState } from "react";
import {
  assignOffice,
  createOffice,
  describeActionError,
  fetchAdminOffices,
  searchAssignableUsers,
  updateOffice,
  workWrite,
} from "../../api/client";
import { Card } from "../../components/Card";
import { EmptyState } from "../../components/EmptyState";
import { MonoLabel } from "../../components/MonoLabel";
import type { Office, UserListItem } from "../../types/admin";

/** Function packages → office permission_template (existing PERMISSIONS). */
const PACKAGES: { key: string; label: string; hint: string; permissions: string[] }[] = [
  { key: "team", label: "Команда", hint: "видеть людей в зоне", permissions: ["panel.view", "people.view"] },
  { key: "tasks", label: "Задачи", hint: "ставить и проверять", permissions: ["panel.view", "tasks.manage"] },
  { key: "broadcasts", label: "Рассылки", hint: "сообщения команде", permissions: ["panel.view", "broadcasts.create"] },
  { key: "events", label: "Мероприятия", hint: "управлять событиями", permissions: ["panel.view", "events.manage"] },
  { key: "media", label: "Медиа", hint: "контент и съёмки", permissions: ["panel.view", "tasks.manage"] },
];

function uniquePermissions(keys: string[]): string[] {
  const set = new Set<string>();
  for (const key of keys) {
    const pack = PACKAGES.find((item) => item.key === key);
    pack?.permissions.forEach((permission) => set.add(permission));
  }
  return Array.from(set);
}

export function AdminAppointLeaderScreen() {
  const [offices, setOffices] = useState<Office[] | "loading" | "error">("loading");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<UserListItem[]>([]);
  const [userId, setUserId] = useState<number | null>(null);
  const [officeId, setOfficeId] = useState<number | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [packages, setPackages] = useState<string[]>(["team", "tasks"]);
  const [alsoLeaderRole, setAlsoLeaderRole] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setOffices("loading");
    try {
      setOffices(await fetchAdminOffices());
    } catch {
      setOffices("error");
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (query.trim().length < 2) {
      setCandidates([]);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void searchAssignableUsers(query.trim())
        .then((items) => {
          if (active) setCandidates(items.slice(0, 8));
        })
        .catch(() => {
          if (active) setCandidates([]);
        });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  const selectedUser = useMemo(
    () => candidates.find((item) => item.id === userId) ?? null,
    [candidates, userId],
  );

  const preview = uniquePermissions(packages);

  const togglePackage = (key: string) => {
    setPackages((current) => (current.includes(key) ? current.filter((item) => item !== key) : [...current, key]));
  };

  const appoint = async () => {
    if (!userId || packages.length === 0) {
      setError("Выбери человека и хотя бы один пакет функций.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      let targetId = officeId;
      const template = uniquePermissions(packages);
      if (!targetId) {
        const title = newTitle.trim() || `Руководитель · ${selectedUser?.first_name ?? userId}`;
        const created = await createOffice(title, "Назначение через пакет функций", template);
        targetId = created.id;
      } else {
        await updateOffice(targetId, { permission_template: template });
      }
      await assignOffice(targetId, userId);
      if (alsoLeaderRole) {
        try {
          await workWrite(`team/${userId}/leader`, { enabled: true });
        } catch {
          // Executive-only; office rights still applied.
        }
      }
      setMessage("Назначено. Функции открыты по выбранным пакетам.");
      setQuery("");
      setCandidates([]);
      setUserId(null);
      setNewTitle("");
      await reload();
    } catch (err) {
      setError(describeActionError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <div>
        <MonoLabel tone="violet">Назначение</MonoLabel>
        <h2 style={{ margin: "0.35rem 0 0", fontSize: "1.35rem" }}>Назначить руководителя</h2>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.88rem", lineHeight: 1.45 }}>
          Человек → пакеты функций → подтвердить. Ранг и должность — разные вещи: здесь открываются права должности.
        </p>
      </div>

      <Card style={{ display: "grid", gap: "0.75rem" }}>
        <label style={{ display: "grid", gap: "0.35rem" }}>
          <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>Кого назначить</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Имя или @username"
            autoComplete="off"
          />
        </label>
        {candidates.length > 0 && (
          <div style={{ display: "grid", gap: "0.4rem" }}>
            {candidates.map((person) => {
              const active = person.id === userId;
              const name = `${person.first_name}${person.last_name ? ` ${person.last_name}` : ""}`;
              return (
                <button
                  key={person.id}
                  type="button"
                  onClick={() => setUserId(person.id)}
                  style={{
                    textAlign: "left",
                    border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                    background: active ? "var(--era-tint-violet)" : "var(--era-surface-2)",
                  }}
                >
                  <strong>{name}</strong>
                  <span style={{ display: "block", color: "var(--era-text-secondary)", fontSize: "0.8rem" }}>
                    {person.username ? `@${person.username}` : `id ${person.id}`}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </Card>

      <Card style={{ display: "grid", gap: "0.75rem" }}>
        <strong>Пакеты функций</strong>
        <div style={{ display: "grid", gap: "0.45rem" }}>
          {PACKAGES.map((pack) => {
            const active = packages.includes(pack.key);
            return (
              <button
                key={pack.key}
                type="button"
                onClick={() => togglePackage(pack.key)}
                style={{
                  textAlign: "left",
                  border: active ? "1px solid var(--era-violet)" : "1px solid var(--era-border)",
                  background: active ? "var(--era-tint-violet)" : "var(--era-surface)",
                }}
              >
                <strong>{pack.label}</strong>
                <span style={{ display: "block", color: "var(--era-text-secondary)", fontSize: "0.8rem" }}>{pack.hint}</span>
              </button>
            );
          })}
        </div>
        {preview.length > 0 && (
          <p style={{ margin: 0, color: "var(--era-text-secondary)", fontSize: "0.78rem" }}>
            Откроется: {preview.join(" · ")}
          </p>
        )}
        <label style={{ display: "flex", gap: "0.55rem", alignItems: "center", fontSize: "0.88rem" }}>
          <input type="checkbox" checked={alsoLeaderRole} onChange={(event) => setAlsoLeaderRole(event.target.checked)} />
          Также статус «Лидер» в режиме команды (если есть право)
        </label>
      </Card>

      <Card style={{ display: "grid", gap: "0.75rem" }}>
        <strong>Должность</strong>
        {offices === "loading" && <p style={{ margin: 0, color: "var(--era-text-muted)" }}>Загрузка должностей…</p>}
        {offices === "error" && <EmptyState text="Не удалось загрузить должности." />}
        {Array.isArray(offices) && (
          <select
            value={officeId ?? ""}
            onChange={(event) => setOfficeId(event.target.value ? Number(event.target.value) : null)}
          >
            <option value="">Создать новую под пакеты</option>
            {offices.filter((office) => office.is_active).map((office) => (
              <option key={office.id} value={office.id}>
                {office.title}
              </option>
            ))}
          </select>
        )}
        {!officeId && (
          <input
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Название должности (необязательно)"
          />
        )}
      </Card>

      {error && <p style={{ margin: 0, color: "var(--era-error)", fontSize: "0.85rem" }}>{error}</p>}
      {message && <p style={{ margin: 0, color: "var(--era-success)", fontSize: "0.85rem" }}>{message}</p>}

      <button type="button" className="era-btn-signal" disabled={busy || !userId || packages.length === 0} onClick={() => void appoint()}>
        {busy ? "Назначаем…" : "Назначить и открыть функции"}
      </button>
    </div>
  );
}
