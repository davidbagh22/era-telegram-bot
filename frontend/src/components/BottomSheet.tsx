import type { ReactNode } from "react";

interface BottomSheetProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

/** Slides up from the bottom — the mobile-idiomatic equivalent of Modal.tsx
 * for this touch-only app (see frontend/e2e/*.spec.ts's fixed mobile
 * viewport). Prefer this over Modal for anything the user reaches for
 * with a thumb: confirmations on a card's own action row, quick pickers,
 * short in-context forms. Reach for Modal instead only when the content
 * genuinely wants to be centered (e.g. a first-load informational
 * dialog). See docs/UI_DESIGN_SYSTEM.md. */
export function BottomSheet({ open, onClose, title, children }: BottomSheetProps) {
  if (!open) {
    return null;
  }

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
          borderTopLeftRadius: "var(--era-radius-sheet)",
          borderTopRightRadius: "var(--era-radius-sheet)",
          background: "var(--era-surface)",
          boxShadow: "var(--era-shadow-overlay)",
          padding: "1.25rem 1.25rem calc(1.25rem + env(safe-area-inset-bottom, 0px))",
          zIndex: 41,
        }}
      >
        <div
          style={{
            width: "2.5rem",
            height: "0.25rem",
            borderRadius: "var(--era-radius-pill)",
            background: "var(--era-border)",
            margin: "0 auto 1rem",
          }}
          aria-hidden="true"
        />
        {title && (
          <h2 style={{ fontFamily: "var(--era-font-display)", fontSize: "var(--era-text-xl)", margin: "0 0 0.75rem" }}>
            {title}
          </h2>
        )}
        {children}
      </div>
    </div>
  );
}
