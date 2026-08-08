import { useState } from "react";
import { fetchAdminUsers } from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import { ROLE_LABELS, ROLE_OPTIONS } from "./roleLabels";

const inputStyle = {
  fontFamily: "var(--era-font-body)",
  padding: "0.625rem",
  borderRadius: "0.625rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-surface)",
  color: "var(--era-text)",
} as const;

interface PeopleListProps {
  onSelect: (userId: number) => void;
}

// The Mini App equivalent of the bot's `admin:participants` inline-keyboard
// list (app/handlers/admin/rights_block6.py) — the single biggest admin
// capability gap: previously the only way to reach a specific participant
// (not just a pending application) was through the bot itself.
export function PeopleList({ onSelect }: PeopleListProps) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const state = useAsync(
    () => fetchAdminUsers({ query, role: role || undefined, limit: 50 }),
    [query, role],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          placeholder="Имя, username или Telegram ID"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          style={{ ...inputStyle, flex: 1 }}
        />
        <select value={role} onChange={(event) => setRole(event.target.value)} style={inputStyle}>
          <option value="">Все роли</option>
          {ROLE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </div>

      {state.status === "loading" && <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>}
      {state.status === "error" && <EmptyState text="Не удалось загрузить список участников." />}
      {state.status === "ready" && state.data.items.length === 0 && (
        <EmptyState text="Никого не найдено." />
      )}
      {state.status === "ready" &&
        state.data.items.map((item) => (
          <Card key={item.id} style={{ padding: "0.75rem 1rem" }}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              style={{
                all: "unset",
                cursor: "pointer",
                display: "flex",
                width: "100%",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <span>
                <strong>
                  {item.first_name} {item.last_name ?? ""}
                </strong>
                <br />
                <span style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
                  {ROLE_LABELS[item.role] ?? item.role}
                  {item.username ? ` · @${item.username}` : ""}
                </span>
              </span>
              <span style={{ display: "flex", gap: "0.375rem", flexShrink: 0 }}>
                {item.is_blocked && <StatusBadge label="Блок" tone="red" />}
                {item.is_archived && <StatusBadge label="Архив" tone="neutral" />}
              </span>
            </button>
          </Card>
        ))}
      {state.status === "ready" && state.data.total > state.data.items.length && (
        <p style={{ color: "var(--era-text-muted)", fontSize: "0.8125rem", textAlign: "center", margin: 0 }}>
          Показаны первые {state.data.items.length} из {state.data.total}. Уточните поиск.
        </p>
      )}
    </div>
  );
}
