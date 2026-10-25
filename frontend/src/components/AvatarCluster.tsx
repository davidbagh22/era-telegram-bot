import { InitialsAvatar } from "./InitialsAvatar";

interface ClusterPerson {
  id: number | string;
  firstName: string;
  lastName?: string | null;
}

interface AvatarClusterProps {
  people: ClusterPerson[];
  max?: number;
  size?: "sm" | "md";
  onSelect?: (id: ClusterPerson["id"]) => void;
}

/** Overlapping avatar cluster for Community (ToR §20) — replaces a plain
 * user list with a denser, more human arrangement. */
export function AvatarCluster({ people, max = 6, size = "md", onSelect }: AvatarClusterProps) {
  const px = size === "sm" ? 32 : 40;
  const shown = people.slice(0, max);
  const overflow = people.length - shown.length;

  return (
    <div style={{ display: "flex", alignItems: "center" }}>
      {shown.map((person, index) => {
        const avatar = (
          <div
            key={person.id}
            style={{
              marginLeft: index === 0 ? 0 : -px * 0.32,
              zIndex: shown.length - index,
              borderRadius: "50%",
              border: "2px solid var(--era-surface)",
              boxShadow: "var(--era-shadow-soft)",
            }}
          >
            <InitialsAvatar firstName={person.firstName} lastName={person.lastName} size={size} />
          </div>
        );
        if (!onSelect) return avatar;
        return (
          <button
            key={person.id}
            type="button"
            onClick={() => onSelect(person.id)}
            aria-label={[person.firstName, person.lastName].filter(Boolean).join(" ")}
            style={{
              all: "unset",
              cursor: "pointer",
              marginLeft: index === 0 ? 0 : -px * 0.32,
              zIndex: shown.length - index,
              borderRadius: "50%",
              border: "2px solid var(--era-surface)",
              boxShadow: "var(--era-shadow-soft)",
              lineHeight: 0,
            }}
          >
            <InitialsAvatar firstName={person.firstName} lastName={person.lastName} size={size} />
          </button>
        );
      })}
      {overflow > 0 && (
        <div
          style={{
            marginLeft: -px * 0.32,
            width: px,
            height: px,
            borderRadius: "50%",
            border: "2px solid var(--era-surface)",
            background: "var(--era-surface-2)",
            color: "var(--era-text-secondary)",
            display: "grid",
            placeItems: "center",
            fontSize: px * 0.36,
            fontWeight: 700,
          }}
        >
          +{overflow}
        </div>
      )}
    </div>
  );
}
