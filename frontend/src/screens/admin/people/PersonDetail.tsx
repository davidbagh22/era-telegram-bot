import { useCallback, useState } from "react";
import {
  awardUserBadge,
  awardUserPoints,
  changeUserRole,
  describeActionError,
  fetchAdminUserDetail,
  setUserArchived,
  setUserBlocked,
  toggleUserPermission,
} from "../../../api/client";
import { Card } from "../../../components/Card";
import { EmptyState } from "../../../components/EmptyState";
import { StatusBadge } from "../../../components/StatusBadge";
import { useAsync } from "../../../hooks/useAsync";
import type { UserDetail } from "../../../types/admin";
import { PERMISSION_LABELS, ROLE_OPTIONS } from "./roleLabels";

const inputStyle = {
  fontFamily: "var(--era-font-body)",
  padding: "0.625rem",
  borderRadius: "0.625rem",
  border: "1px solid var(--era-border)",
  background: "var(--era-bg)",
  color: "var(--era-text)",
  width: "100%",
} as const;

const rowStyle = { display: "flex", justifyContent: "space-between", gap: "0.75rem" } as const;

interface PersonDetailProps {
  userId: number;
  onBack: () => void;
}

export function PersonDetail({ userId, onBack }: PersonDetailProps) {
  const [refreshKey, setRefreshKey] = useState(0);
  const state = useAsync(() => fetchAdminUserDetail(userId), [userId, refreshKey]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pointsAmount, setPointsAmount] = useState("");
  const [pointsReason, setPointsReason] = useState("");
  const [badgeReasons, setBadgeReasons] = useState<Record<number, string>>({});

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  const runAction = useCallback(
    async (action: () => Promise<unknown>) => {
      setBusy(true);
      setError(null);
      try {
        await action();
        refresh();
      } catch (err) {
        setError(describeActionError(err));
      } finally {
        setBusy(false);
      }
    },
    [refresh],
  );

  if (state.status === "loading") {
    return <p style={{ color: "var(--era-text-muted)" }}>Загрузка…</p>;
  }
  if (state.status === "error") {
    return <EmptyState text="Не удалось загрузить участника." />;
  }

  const person: UserDetail = state.data;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
      <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
        ← К списку
      </button>

      {error && <p style={{ color: "var(--era-error)", fontSize: "0.8125rem", margin: 0 }}>{error}</p>}

      <Card>
        <div style={rowStyle}>
          <div>
            <strong style={{ fontSize: "1.0625rem" }}>
              {person.first_name} {person.last_name ?? ""}
            </strong>
            <p style={{ margin: "0.25rem 0 0", color: "var(--era-text-muted)", fontSize: "0.8125rem" }}>
              {person.username ? `@${person.username}` : person.telegram_id} · #{person.id}
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.375rem", flexShrink: 0 }}>
            {person.is_blocked && <StatusBadge label="Заблокирован" tone="red" />}
            {person.is_archived && <StatusBadge label="В архиве" tone="neutral" />}
          </div>
        </div>
        <dl style={{ margin: "0.75rem 0 0", display: "grid", gridTemplateColumns: "auto 1fr", gap: "0.25rem 0.75rem", fontSize: "0.875rem" }}>
          <dt style={{ color: "var(--era-text-muted)" }}>Город</dt>
          <dd style={{ margin: 0 }}>{person.city ?? "—"}</dd>
          <dt style={{ color: "var(--era-text-muted)" }}>Телефон</dt>
          <dd style={{ margin: 0 }}>{person.phone ?? "—"}</dd>
          <dt style={{ color: "var(--era-text-muted)" }}>Email</dt>
          <dd style={{ margin: 0 }}>{person.email ?? "—"}</dd>
          <dt style={{ color: "var(--era-text-muted)" }}>Занятие</dt>
          <dd style={{ margin: 0 }}>{person.occupation ?? "—"}</dd>
          <dt style={{ color: "var(--era-text-muted)" }}>Баланс</dt>
          <dd style={{ margin: 0 }}>{person.points_balance} баллов</dd>
          <dt style={{ color: "var(--era-text-muted)" }}>Портфолио</dt>
          <dd style={{ margin: 0 }}>{person.portfolio_count}</dd>
        </dl>
        {person.motivation && (
          <p style={{ margin: "0.75rem 0 0", fontSize: "0.875rem" }}>«{person.motivation}»</p>
        )}
        {person.social_links.length > 0 && (
          <p style={{ margin: "0.5rem 0 0", fontSize: "0.8125rem", color: "var(--era-text-muted)" }}>
            {person.social_links.map((link) => `${link.platform}: ${link.url}`).join(" · ")}
          </p>
        )}
      </Card>

      {person.can_manage && (
        <Card>
          <strong>Роль и доступ</strong>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
            <select
              value={person.role}
              disabled={busy}
              onChange={(event) => runAction(() => changeUserRole(userId, event.target.value))}
              style={{ ...inputStyle, width: "auto", flex: "1 1 12rem" }}
            >
              {ROLE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
            <button
              type="button"
              disabled={busy}
              onClick={() => runAction(() => setUserBlocked(userId, !person.is_blocked))}
            >
              {person.is_blocked ? "Разблокировать" : "Заблокировать"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => runAction(() => setUserArchived(userId, !person.is_archived))}
            >
              {person.is_archived ? "Вернуть из архива" : "В архив"}
            </button>
          </div>
        </Card>
      )}

      {person.can_manage_permissions && (
        <Card>
          <strong>Технические права</strong>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem", marginTop: "0.5rem" }}>
            {Object.entries(person.permissions).map(([permission, enabled]) => (
              <label
                key={permission}
                style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem", cursor: "pointer" }}
              >
                <input
                  type="checkbox"
                  checked={enabled}
                  disabled={busy}
                  onChange={() => runAction(() => toggleUserPermission(userId, permission))}
                />
                {PERMISSION_LABELS[permission] ?? permission}
              </label>
            ))}
          </div>
        </Card>
      )}

      {person.can_award_points && (
        <Card>
          <strong>Начислить или списать баллы</strong>
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem", flexWrap: "wrap" }}>
            <input
              type="number"
              placeholder="±баллы"
              value={pointsAmount}
              onChange={(event) => setPointsAmount(event.target.value)}
              style={{ ...inputStyle, width: "auto", flex: "1 1 6rem" }}
            />
            <input
              type="text"
              placeholder="Причина"
              value={pointsReason}
              onChange={(event) => setPointsReason(event.target.value)}
              style={{ ...inputStyle, flex: "2 1 10rem" }}
            />
            <button
              type="button"
              className="era-btn-primary"
              disabled={busy || !pointsAmount || !pointsReason.trim()}
              onClick={() =>
                runAction(async () => {
                  await awardUserPoints(userId, Number(pointsAmount), pointsReason.trim());
                  setPointsAmount("");
                  setPointsReason("");
                })
              }
            >
              Применить
            </button>
          </div>
        </Card>
      )}

      {person.can_award_points && (person.badges.length > 0 || person.available_badges.length > 0) && (
        <Card>
          <strong>Знаки отличия</strong>
          {person.badges.length > 0 && (
            <p style={{ margin: "0.5rem 0", fontSize: "0.875rem", color: "var(--era-text-muted)" }}>
              Уже есть: {person.badges.map((badge) => badge.name).join(", ")}
            </p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginTop: "0.5rem" }}>
            {person.available_badges.map((badge) => (
              <div key={badge.id} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <input
                  type="text"
                  placeholder={`За что «${badge.name}»?`}
                  value={badgeReasons[badge.id] ?? ""}
                  onChange={(event) =>
                    setBadgeReasons((previous) => ({ ...previous, [badge.id]: event.target.value }))
                  }
                  style={{ ...inputStyle, flex: 1 }}
                />
                <button
                  type="button"
                  disabled={busy || !(badgeReasons[badge.id] ?? "").trim()}
                  onClick={() =>
                    runAction(async () => {
                      await awardUserBadge(userId, badge.id, (badgeReasons[badge.id] ?? "").trim());
                      setBadgeReasons((previous) => ({ ...previous, [badge.id]: "" }));
                    })
                  }
                >
                  Выдать «{badge.name}»
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
