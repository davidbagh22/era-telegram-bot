import type { ReactNode } from "react";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

/** Mobile bottom sheet with a real 44px close target. */
export function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  if (!open) return null;

  return (
    <div
      className="era-overlay-backdrop"
      onClick={onClose}
      style={{ display: "flex", alignItems: "flex-end", justifyContent: "center" }}
    >
      <div
        className="era-bottom-sheet"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: "28rem",
          maxHeight: "min(88dvh, 48rem)",
          overflowY: "auto",
          borderTopLeftRadius: "var(--era-radius-sheet)",
          borderTopRightRadius: "var(--era-radius-sheet)",
          background: "var(--era-surface)",
          boxShadow: "var(--era-shadow-overlay)",
          padding: "0.75rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom, 0px))",
          zIndex: 41,
        }}
      >
        <div
          style={{
            width: "2.5rem",
            height: "0.25rem",
            borderRadius: "var(--era-radius-pill)",
            background: "var(--era-border)",
            margin: "0 auto 0.55rem",
          }}
          aria-hidden="true"
        />
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.75rem", marginBottom: title ? "0.75rem" : "0.35rem" }}>
          {title ? (
            <h2 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)", margin: 0, lineHeight: 1.2 }}>
              {title}
            </h2>
          ) : <span />}
          <button
            type="button"
            aria-label="Закрыть"
            onClick={onClose}
            style={{
              width: 44,
              height: 44,
              minWidth: 44,
              minHeight: 44,
              padding: 0,
              borderRadius: "50%",
              border: "1px solid var(--era-border)",
              background: "var(--era-bg-subtle)",
              color: "var(--era-text)",
              fontSize: "1.25rem",
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
