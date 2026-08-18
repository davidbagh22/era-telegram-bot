const SIZES = { sm: 32, md: 48, lg: 56 } as const;

interface AvatarProps {
  firstName: string;
  lastName?: string | null;
  size?: keyof typeof SIZES;
}

/** ERA doesn't have a profile-photo pipeline into the Mini App API (the
 * Bot's own admin-facing photo review is a separate, Bot-only surface —
 * see docs/BOT_VS_MINIAPP_AUDIT.md) — so the avatar was always going to be
 * a placeholder, not an <img>. This is a deliberate, permanent choice, not
 * a "photo support coming later" placeholder.
 *
 * It's a flame, not initials — this component is only ever used to show
 * "you" (Home's own hero, Profile's own header; grep before assuming
 * otherwise if you're tempted to reuse it for a roster/list of *other*
 * people, where initials would actually earn their keep by telling people
 * apart). A flame doesn't need to distinguish you from anyone else, and it
 * reuses the bot's own "🔥 Открыть ЭРА" mark instead of yet another
 * generic initials-in-a-circle avatar. */
export function Avatar({ firstName, lastName, size = "md" }: AvatarProps) {
  const px = SIZES[size];
  const name = [firstName, lastName].filter(Boolean).join(" ").trim() || "участник ЭРА";
  return (
    <div
      style={{
        width: px,
        height: px,
        borderRadius: "50%",
        background: "var(--era-gradient-signal)",
        boxShadow: `0 0 0 1px rgba(255,255,255,0.5) inset, 0 ${px * 0.12}px ${px * 0.32}px rgba(99, 44, 255, 0.3)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
      role="img"
      aria-label={`Аватар: ${name}`}
    >
      <svg
        width={px * 0.52}
        height={px * 0.52}
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        {/* One simple flame silhouette — outer tongue in gold, inner core
            in white, both drawn as plain teardrops (M...C...C...Z) rather
            than an elaborate multi-curve illustration. */}
        <path
          d="M12 2C9 6 6.5 9.3 6.5 13a5.5 5.5 0 0 0 11 0C17.5 9.3 15 6 12 2Z"
          fill="var(--era-gold)"
        />
        <path
          d="M12 8c-1.6 2.1-3 3.9-3 5.8a3 3 0 0 0 6 0C15 11.9 13.6 10.1 12 8Z"
          fill="#fff"
          fillOpacity="0.95"
        />
      </svg>
    </div>
  );
}
