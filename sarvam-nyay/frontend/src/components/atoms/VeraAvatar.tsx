/**
 * VeraAvatar — branded avatar for the AI assistant.
 *
 * Two visual states:
 *  - idle:      soft gold halo, calm
 *  - thinking:  the halo pulses (`animate-veraPulse`) to signal that the
 *               assistant is actively working
 *
 * The halo is a sibling absolutely-positioned blur element so it never
 * affects layout. The Brain icon stays crisp on top.
 *
 * Respects `prefers-reduced-motion` — the pulse is gated by Tailwind's
 * `motion-safe:` variant.
 */

import { Brain } from "lucide-react";
import { clsx } from "clsx";

interface VeraAvatarProps {
  size?: "sm" | "md" | "lg";
  thinking?: boolean;
  className?: string;
}

const SIZE_MAP = {
  sm: { wrap: "w-8 h-8",  icon: "w-4 h-4",  halo: "inset-[-6px]" },
  md: { wrap: "w-10 h-10", icon: "w-5 h-5",  halo: "inset-[-8px]" },
  lg: { wrap: "w-16 h-16", icon: "w-8 h-8",  halo: "inset-[-12px]" },
} as const;

export function VeraAvatar({ size = "md", thinking = false, className }: VeraAvatarProps) {
  const s = SIZE_MAP[size];

  return (
    <div className={clsx("relative inline-flex items-center justify-center", className)} aria-hidden="true">
      {/* Halo — soft gold glow that pulses when thinking */}
      <span
        className={clsx(
          "absolute rounded-full bg-gold-400/50 blur-md",
          s.halo,
          thinking ? "motion-safe:animate-veraPulse" : "opacity-60",
        )}
      />
      {/* Inner solid circle */}
      <span
        className={clsx(
          "relative inline-flex items-center justify-center rounded-full",
          "bg-gradient-to-br from-gold-400 to-gold-600 text-white shadow-glow",
          s.wrap,
        )}
      >
        <Brain className={s.icon} />
      </span>
    </div>
  );
}
