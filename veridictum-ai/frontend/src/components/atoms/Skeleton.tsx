/**
 * Skeleton — premium shimmer loader.
 *
 * Replaces the previous `animate-pulse` opacity flash with a gradient sweep
 * that feels closer to Linear / Vercel / Stripe loaders. Honors
 * `prefers-reduced-motion` (collapses to a flat tinted block).
 */

import { clsx } from "clsx";
import { useReducedMotion } from "@/hooks/useReducedMotion";

interface SkeletonProps {
  className?: string;
  /** Visual variant — defaults to "default" (lightest). */
  tone?: "default" | "dark";
}

export function Skeleton({ className, tone = "default" }: SkeletonProps) {
  const reduce = useReducedMotion();
  const base =
    tone === "dark"
      ? "bg-navy-700/40"
      : "bg-gradient-to-r from-gray-100 via-gray-50 to-gray-100";

  return (
    <div
      className={clsx(
        "relative overflow-hidden rounded-md",
        base,
        // The sweep — only rendered when motion is allowed.
        !reduce &&
          "before:absolute before:inset-0 before:-translate-x-full " +
            "before:animate-[shimmer_1.6s_ease-in-out_infinite] " +
            "before:bg-gradient-to-r before:from-transparent " +
            "before:via-white/70 before:to-transparent",
        className,
      )}
      aria-hidden="true"
    />
  );
}
