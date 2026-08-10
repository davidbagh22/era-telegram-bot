const SIZES = { sm: 32, md: 48, lg: 72 } as const;

interface AvatarProps {
  firstName: string;
  lastName?: string | null;
  size?: keyof typeof SIZES;
}

function initials(firstName: string, lastName?: string | null): string {
  const first = firstName.trim().charAt(0);
  const last = (lastName ?? "").trim().charAt(0);
  return (first + last).toUpperCase() || "?";
}

/** ERA doesn't have a profile-photo pipeline into the Mini App API (the
 * Bot's own admin-facing photo review is a separate, Bot-only surface —
 * see docs/BOT_VS_MINIAPP_AUDIT.md) — so the avatar is always initials on
 * the brand gradient, not an <img>. This is a deliberate, permanent
 * choice, not a "photo support coming later" placeholder. */
export function Avatar({ firstName, lastName, size = "md" }: AvatarProps) {
  const px = SIZES[size];
  return (
    <div
      style={{
        width: px,
        height: px,
        borderRadius: "50%",
        background: "var(--era-gradient)",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "var(--era-font-display)",
        fontSize: px * 0.4,
        fontWeight: 600,
        flexShrink: 0,
        userSelect: "none",
      }}
      aria-hidden="true"
    >
      {initials(firstName, lastName)}
    </div>
  );
}
