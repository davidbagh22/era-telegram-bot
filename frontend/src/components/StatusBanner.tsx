interface StatusBannerProps {
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

export function StatusBanner({ title, description, actionLabel, onAction }: StatusBannerProps) {
  return (
    <div
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
          style={{ marginTop: "0.5rem" }}
        >
          {actionLabel}
        </button>
      )}
    </div>
  );
}
