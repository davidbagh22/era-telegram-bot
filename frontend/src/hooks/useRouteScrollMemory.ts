import { useEffect } from "react";

const SCROLL_PREFIX = "era:scroll:";

function scrollKey(hash: string): string {
  return `${SCROLL_PREFIX}${hash || "#/home"}`;
}

export function useRouteScrollMemory(): void {
  useEffect(() => {
    if (!("scrollRestoration" in window.history)) return;
    const previousMode = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";
    let previousHash = window.location.hash || "#/home";

    const remember = () => {
      try { window.sessionStorage.setItem(scrollKey(previousHash), String(window.scrollY)); } catch { /* storage may be restricted */ }
    };

    const restore = () => {
      remember();
      previousHash = window.location.hash || "#/home";
      let target = 0;
      try {
        const raw = window.sessionStorage.getItem(scrollKey(previousHash));
        if (raw !== null) target = Math.max(0, Number(raw) || 0);
      } catch { target = 0; }
      window.requestAnimationFrame(() => window.requestAnimationFrame(() => window.scrollTo({ top: target, behavior: "auto" })));
    };

    window.addEventListener("hashchange", restore);
    window.addEventListener("beforeunload", remember);
    return () => {
      remember();
      window.removeEventListener("hashchange", restore);
      window.removeEventListener("beforeunload", remember);
      window.history.scrollRestoration = previousMode;
    };
  }, []);
}
