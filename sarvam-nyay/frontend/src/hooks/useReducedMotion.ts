/**
 * useReducedMotion — respects the user's OS-level "reduce motion" setting.
 *
 * Returns `true` when `prefers-reduced-motion: reduce` matches. Gate every
 * non-essential animation on this so we don't trigger vestibular disorders
 * or burn battery on devices that opted out of motion.
 *
 * Note: we don't simply import this from framer-motion to avoid a hard
 * coupling — the hook is also used by Recharts and by plain CSS-driven
 * components.
 */

import { useEffect, useState } from "react";

const MEDIA_QUERY = "(prefers-reduced-motion: reduce)";

export function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(MEDIA_QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia(MEDIA_QUERY);
    const onChange = (e: MediaQueryListEvent): void => setReduce(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return reduce;
}
