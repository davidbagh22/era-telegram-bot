/**
 * On-screen keyboard awareness for the Mini App.
 *
 * Telegram Android resizes the WebView, iOS shrinks only the visual viewport.
 * Either way the fixed bottom bars would stack on top of the keyboard and cover
 * the field being edited. While an editable control has focus and the viewport
 * is clearly shorter than its baseline we mark <html data-keyboard="open">;
 * CSS hides `[data-era-hide-on-keyboard]` bars, and the focused field is
 * scrolled clear of whatever remains.
 */
const SHRINK_RATIO = 0.78;
const EDITABLE_INPUT_TYPES = new Set([
  "text", "search", "email", "url", "tel", "password", "number", "date", "datetime-local", "time", "month", "week",
]);

export function isEditableElement(element: Element | null): boolean {
  if (!(element instanceof HTMLElement)) return false;
  if (element instanceof HTMLTextAreaElement) return true;
  if (element instanceof HTMLInputElement) return EDITABLE_INPUT_TYPES.has(element.type);
  return element.isContentEditable;
}

export function keyboardLikelyOpen(viewportHeight: number, baselineHeight: number, activeElement: Element | null): boolean {
  return viewportHeight < baselineHeight * SHRINK_RATIO && isEditableElement(activeElement);
}

let installed = false;

export function installKeyboardAwareness(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const viewport = window.visualViewport;
  let baseline = Math.max(window.innerHeight, viewport?.height ?? 0);
  let lastWidth = window.innerWidth;

  const update = () => {
    if (window.innerWidth !== lastWidth) {
      lastWidth = window.innerWidth;
      baseline = Math.max(window.innerHeight, viewport?.height ?? 0);
    }
    const height = Math.min(window.innerHeight, viewport?.height ?? window.innerHeight);
    if (height > baseline) baseline = height;
    const open = keyboardLikelyOpen(height, baseline, document.activeElement);
    const root = document.documentElement;
    if (open) root.dataset.keyboard = "open";
    else delete root.dataset.keyboard;
  };

  const reveal = () => {
    const active = document.activeElement;
    if (!isEditableElement(active)) return;
    const visibleBottom = viewport?.height ?? window.innerHeight;
    const rect = (active as HTMLElement).getBoundingClientRect();
    if (rect.bottom > visibleBottom - 16 || rect.top < 0) {
      const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      (active as HTMLElement).scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
    }
  };

  document.addEventListener("focusin", () => {
    update();
    window.setTimeout(() => { update(); reveal(); }, 320);
  });
  document.addEventListener("focusout", () => window.setTimeout(update, 60));
  window.addEventListener("resize", update);
  viewport?.addEventListener("resize", update);
}
