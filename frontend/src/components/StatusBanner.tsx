interface StatusBannerProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  /** Soft status vs blocking error. Defaults to alert so dead-end loads announce. */
  tone?: "alert" | "status";
}

export function StatusBanner({
  title,
  description,
  actionLabel,
  onAction,
  tone = "alert",
}: StatusBannerProps) {
  return (
    <div
      role={tone}
      aria-live={tone === "alert" ? "assertive" : "polite"}
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
        alignItems: "center",
        textAlign: "center",
        padding: "calc(2.5rem + env(safe-area-inset-top, 0px)) 1.5rem 2.5rem",
        maxWidth: "28rem",
        margin: "0 auto",
      }}
    >
      <h1 style={{ fontFamily: "var(--era-font-display)", fontSize: "1.25rem", margin: 0 }}>
        {title}
      </h1>
      <p style={{ color: "var(--era-text-muted)", margin: 0 }}>{description}</p>
      {actionLabel && onAction && (
        <button
          type="button"
          className="era-btn-primary"
          onClick={onAction}
          style={{ marginTop: "0.5rem", minHeight: 44 }}
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
