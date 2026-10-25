import { useEffect } from "react";
import type { ReactNode } from "react";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}

/** Centered dialog with a backdrop — for confirmations and short forms
 * that aren't tied to "the thing at the bottom of the screen" the way
 * BottomSheet.tsx's targets are. See docs/UI_DESIGN_SYSTEM.md for when to
 * reach for this vs. BottomSheet. */
export function Modal({ open, onClose, title, children }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="era-overlay-backdrop"
      onClick={onClose}
      style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: "1.5rem" }}
    >
      <div
        className="era-modal era-card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: "22rem",
          borderRadius: "var(--era-radius-card)",
          background: "var(--era-surface)",
          boxShadow: "var(--era-shadow-lift)",
          padding: "1.25rem",
          zIndex: 41,
        }}
      >
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
