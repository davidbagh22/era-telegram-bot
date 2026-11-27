import { useEffect, useState } from "react";

const ENTRANCE_MS = 520;

/**
 * Class list for a screen root that plays its staggered entrance exactly once.
 *
 * `.era-stagger` animates children by position (`:nth-child`). If it stays on
 * after the entrance, any sibling that is later inserted or removed (async
 * cards, conditional sections) shifts positions and re-triggers animations on
 * elements that were already on screen. Dropping the class once the entrance
 * has finished makes later DOM changes inert.
 *
 * `active` is true once the screen root is actually rendered (not a skeleton).
 */
export function useEntranceClass(active = true): string {
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    if (!active) return undefined;
    const timer = window.setTimeout(() => setSettled(true), ENTRANCE_MS);
    return () => window.clearTimeout(timer);
  }, [active]);
  return settled ? "era-page era-page--settled" : "era-page era-stagger";
}
