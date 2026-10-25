const SIZES = { sm: 32, md: 40 } as const;

const TINTS = [
  { bg: "var(--era-tint-violet)", fg: "var(--era-violet)" },
  { bg: "var(--era-tint-red)", fg: "var(--era-red)" },
  { bg: "var(--era-tint-gold)", fg: "var(--era-gold-ink)" },
  { bg: "var(--era-surface-2)", fg: "var(--era-magenta)" },
];

interface InitialsAvatarProps {
  firstName: string;
  lastName?: string | null;
  size?: keyof typeof SIZES;
}

/** Roster/list avatar — initials in a tinted circle, distinct from the
 * flame Avatar (see Avatar.tsx's own docstring: the flame is reserved for
 * "you", initials are what actually tell a list of *other* people apart).
 * Used for admin lists of participants (PeopleList, applications) where a
 * roster of names benefits from a quick visual anchor per row. The tint
 * cycles by name (a stable hash of the full name), not by any real
 * attribute — purely so adjacent rows in a list don't blur into a wall of
 * identical gray circles, not meant to encode role/status. */
export function InitialsAvatar({ firstName, lastName, size = "sm" }: InitialsAvatarProps) {
  const px = SIZES[size];
  const initials = [firstName, lastName]
    .filter(Boolean)
    .map((part) => part!.trim()[0]?.toUpperCase() ?? "")
    .join("") || "?";
  const name = [firstName, lastName].filter(Boolean).join(" ");
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) % TINTS.length;
  }
  const tint = TINTS[hash];

  return (
    <div
      style={{
        width: px,
        height: px,
        borderRadius: "50%",
        background: tint.bg,
        color: tint.fg,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        fontFamily: "var(--era-font-display)",
        fontSize: px * 0.4,
        fontWeight: 700,
      }}
      aria-hidden="true"
    >
      {initials}
    </div>
  );
}
