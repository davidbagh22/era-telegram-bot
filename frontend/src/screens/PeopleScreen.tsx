import { useEffect, useState } from "react";
import { fetchCommunityUsers, type CommunityUser } from "../api/communityUsers";
import { EmptyState } from "../components/EmptyState";
import { MonoLabel } from "../components/MonoLabel";
import { SkeletonList } from "../components/Skeleton";

interface PeopleScreenProps {
  onOpenUser?: (userId: number) => void;
  onBack?: () => void;
}

export function PeopleScreen({ onOpenUser, onBack }: PeopleScreenProps) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [department, setDepartment] = useState<string | null>(null);
  const [items, setItems] = useState<CommunityUser[] | "loading" | "error">("loading");
  const [total, setTotal] = useState(0);
  const [reloadTick, setReloadTick] = useState(0);
  const [offset, setOffset] = useState(0);
  const [departments, setDepartments] = useState<string[]>([]);

  useEffect(() => {
    let active = true;
    setItems("loading");
    void fetchCommunityUsers({
      q: submitted || undefined,
      department: department || undefined,
      limit: 40,
      offset,
    })
      .then((result) => {
        if (!active) return;
        setItems(result.items);
        setTotal(result.total);
        setDepartments(previous => Array.from(new Set([
          ...previous, ...result.items.flatMap(person => person.departments),
        ])).sort());
      })
      .catch(() => {
        if (active) setItems("error");
      });
    return () => {
      active = false;
    };
  }, [submitted, department, reloadTick, offset]);

  return (
    <div className="era-page" style={{ padding: "1.15rem 1.15rem var(--era-page-bottom-safe)", display: "flex", flexDirection: "column", gap: "1rem" }}>
      {onBack && (
        <button type="button" onClick={onBack} style={{ alignSelf: "flex-start" }}>
          ← Орбита
        </button>
      )}
      <header>
        <MonoLabel>Орбита</MonoLabel>
        <h1 style={{ margin: "0.35rem 0 0", fontFamily: "var(--era-font-display)", fontSize: "1.8rem" }}>Люди</h1>
        <p style={{ margin: "0.4rem 0 0", color: "var(--era-text-secondary)", fontSize: "0.9rem" }}>
          Участники ЭРА по разрешённым направлениям. Контакты не раскрываются.
        </p>
      </header>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          setSubmitted(query.trim()); setOffset(0);
        }}
        style={{ display: "flex", gap: "0.5rem" }}
      >
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Найти человека"
          aria-label="Найти человека"
        />
        <button type="submit" className="era-btn-primary" style={{ flexShrink: 0, minWidth: 88 }}>
          Найти
        </button>
      </form>

      {departments.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
          <button
            type="button"
            aria-pressed={department === null}
            onClick={() => { setDepartment(null); setOffset(0); }}
            style={{
              minHeight: 36,
              borderRadius: "var(--era-radius-pill)",
              background: department === null ? "var(--era-selected)" : "var(--era-surface)",
              color: department === null ? "var(--era-cyan)" : "var(--era-text-secondary)",
              border: "1px solid var(--era-border)",
              fontSize: "0.78rem",
            }}
          >
            Все
          </button>
          {departments.map((name) => (
            <button
              key={name}
              type="button"
              aria-pressed={department === name}
              onClick={() => { setDepartment(name); setOffset(0); }}
              style={{
                minHeight: 36,
                borderRadius: "var(--era-radius-pill)",
                background: department === name ? "var(--era-selected)" : "var(--era-surface)",
                color: department === name ? "var(--era-cyan)" : "var(--era-text-secondary)",
                border: "1px solid var(--era-border)",
                fontSize: "0.78rem",
              }}
            >
              {name}
            </button>
          ))}
        </div>
      )}

      {items === "loading" && <SkeletonList count={4} />}
      {items === "error" && (
        <EmptyState
          title="Не удалось загрузить людей"
          text="Проверь соединение и попробуй ещё раз."
          actionLabel="Обновить"
          onAction={() => setReloadTick((value) => value + 1)}
        />
      )}
      {Array.isArray(items) && items.length === 0 && (
        <EmptyState text={submitted ? "Никого не нашли по этому запросу." : "Пока нет участников для показа."} />
      )}
      {Array.isArray(items) && items.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
          <p style={{ margin: 0, color: "var(--era-text-faint)", fontSize: "0.78rem" }}>Показано {offset + 1}–{offset + items.length} из {total}</p>
          {items.map((person) => {
            const tags = [...person.departments, ...(person.directions ?? [])].slice(0, 3);
            const initials = person.name
              .split(/\s+/)
              .filter(Boolean)
              .slice(0, 2)
              .map((part) => part[0]?.toUpperCase())
              .join("");
            return (
              <button
                key={person.id}
                type="button"
                onClick={() => onOpenUser?.(person.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.85rem",
                  padding: "0.85rem 0.95rem",
                  borderRadius: "var(--era-radius-lg)",
                  border: "1px solid var(--era-border)",
                  background: "var(--era-glass)",
                  textAlign: "left",
                  width: "100%",
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: "50%",
                    display: "grid",
                    placeItems: "center",
                    background: "var(--era-selected)",
                    color: "var(--era-cyan)",
                    fontWeight: 800,
                    flexShrink: 0,
                  }}
                >
                  {initials || "Э"}
                </span>
                <span style={{ minWidth: 0, flex: 1 }}>
                  <strong style={{ display: "block" }}>{person.name}</strong>
                  <span style={{ display: "block", marginTop: 2, color: "var(--era-text-faint)", fontSize: "0.8rem" }}>
                    {tags.length ? tags.join(" · ") : person.role_label}
                  </span>
                </span>
                <span aria-hidden="true" style={{ color: "var(--era-cyan)" }}>→</span>
              </button>
            );
          })}
          {total > 40 && <div style={{ display: "flex", gap: 8 }}>
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 40))}>← Назад</button>
            <button disabled={offset + items.length >= total} onClick={() => setOffset(offset + 40)}>Далее →</button>
          </div>}
        </div>
      )}
    </div>
  );
}
