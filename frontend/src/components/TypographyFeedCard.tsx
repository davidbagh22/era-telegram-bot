import type { CSSProperties } from "react";

interface TypographyFeedCardProps {
  title: string;
  dateLine: string;
  onClick?: () => void;
  style?: CSSProperties;
}

/**
 * Public feed card: expressive title + one date line only.
 * No poster/cover, badges, CTAs, or nested controls (AURA×ORBIT §7).
 */
export function TypographyFeedCard({ title, dateLine, onClick, style }: TypographyFeedCardProps) {
  return (
    <button
      type="button"
      className="era-typography-feed-card era-card"
      onClick={onClick}
      aria-label={`${title}. ${dateLine}`}
      style={style}
    >
      <h3 className="era-typography-feed-card__title">{title}</h3>
      <p className="era-typography-feed-card__date">{dateLine}</p>
    </button>
  );
}
