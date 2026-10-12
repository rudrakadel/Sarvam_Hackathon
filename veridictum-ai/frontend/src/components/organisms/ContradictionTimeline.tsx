/**
 * ContradictionTimeline — horizontal strip showing where in the testimony
 * each contradiction occurs.
 *
 * Each contradiction is plotted as a colored marker on a horizontal axis
 * keyed by `transcript_timestamp_start`. Severity drives the colour. This
 * gives the attorney a one-glance picture of where in the testimony Vera
 * found conflicts.
 *
 * Design rationale (v2):
 *   - Dots are constrained to the [6%, 90%] range of the strip width so they
 *     never sit on top of the "start of testimony" / "peak @ MM:SS" axis
 *     labels.
 *   - An explicit horizontal axis line runs through the middle of the strip
 *     at 50% so the dots read as "events on a timeline" instead of "dots in
 *     a box".
 *   - Each dot gets a small timestamp label (MM:SS) directly under it,
 *     centred — turns the strip into a self-documenting micro-chart instead
 *     of relying on hover tooltips.
 *   - Tick marks at 25/50/75% to keep the eye anchored.
 *   - Honors prefers-reduced-motion via the shared hook.
 *   - Fully a11y: each dot is a `<button>` with an aria-label, so a screen
 *     reader can announce "Contradiction 1 of 3, CRITICAL severity, at
 *     2 minutes 14 seconds, 94% confidence".
 */

import { motion } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import type { Contradiction } from "@/types";

interface ContradictionTimelineProps {
  contradictions: Contradiction[];
  className?: string;
}

const SEV_COLORS: Record<string, string> = {
  CRITICAL:      "bg-red-500",
  HIGH:          "bg-orange-500",
  MEDIUM:        "bg-amber-500",
  LOW:           "bg-blue-500",
  INFORMATIONAL: "bg-gray-400",
};

const SEV_RING: Record<string, string> = {
  CRITICAL:      "ring-red-200/80 dark:ring-red-500/30",
  HIGH:          "ring-orange-200/80 dark:ring-orange-500/30",
  MEDIUM:        "ring-amber-200/80 dark:ring-amber-500/30",
  LOW:           "ring-blue-200/80 dark:ring-blue-500/30",
  INFORMATIONAL: "ring-gray-200 dark:ring-gray-600",
};

const SEV_LABEL: Record<string, string> = {
  CRITICAL:      "Critical",
  HIGH:          "High",
  MEDIUM:        "Medium",
  LOW:           "Low",
  INFORMATIONAL: "Informational",
};

// The visual track spans 0%–100% of the container, but we constrain the dot
// positions to a sub-range so they never crowd the axis labels.
const TRACK_LEFT_PCT = 6;
const TRACK_RIGHT_PCT = 90;
const TRACK_SPAN = TRACK_RIGHT_PCT - TRACK_LEFT_PCT;

function fmtMMSS(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/** Map a timestamp in seconds → percentage along the visual track. */
function positionFor(ts: number | null | undefined, idx: number, maxTs: number, count: number): number {
  if (ts != null && maxTs > 0) {
    const frac = Math.min(1, Math.max(0, ts / maxTs));
    return TRACK_LEFT_PCT + frac * TRACK_SPAN;
  }
  // No timestamp — distribute by order across the track.
  if (count === 0) return TRACK_LEFT_PCT + TRACK_SPAN / 2;
  return TRACK_LEFT_PCT + ((idx + 1) / (count + 1)) * TRACK_SPAN;
}

export function ContradictionTimeline({ contradictions, className = "" }: ContradictionTimelineProps) {
  const reduce = useReducedMotion();
  if (!contradictions || contradictions.length === 0) return null;

  const withTs = contradictions.filter((c) => c.transcript_timestamp_start != null);
  const maxTs = withTs.length
    ? Math.max(...withTs.map((c) => c.transcript_timestamp_start ?? 0))
    : 0;

  // Build the dot models up-front so the JSX stays clean.
  const dots = contradictions.map((c, i) => {
    const ts = c.transcript_timestamp_start ?? null;
    const left = positionFor(ts, i, maxTs, contradictions.length);
    return {
      key: c.id,
      left,
      ts,
      severity: c.severity,
      confidence: c.confidence_score,
      explanation: c.explanation,
    };
  });

  return (
    <div className={`relative ${className}`} role="group" aria-label="Contradiction timeline">
      <div className="flex items-center justify-between mb-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-700 dark:text-gold-300">
          Contradiction timeline
        </p>
        <p className="text-[10px] text-gray-400 dark:text-gray-500">
          {contradictions.length} found{withTs.length ? ` · spans ${fmtMMSS(maxTs)}` : ""}
        </p>
      </div>

      {/* The track itself — gives the dots vertical space + a baseline. */}
      <div className="relative h-12 rounded-lg bg-gradient-to-r from-navy-50 via-white to-navy-50 dark:from-navy-700/50 dark:via-navy-800/40 dark:to-navy-700/50 border border-navy-100 dark:border-navy-700">
        {/* Baseline — a soft horizontal rule the dots sit on */}
        <div
          className="absolute left-[6%] right-[10%] top-1/2 h-px bg-navy-200/70 dark:bg-navy-600"
          aria-hidden="true"
        />

        {/* Tick marks at 25/50/75% of the TRACK (not the container) */}
        {[0.25, 0.5, 0.75].map((p) => {
          const left = TRACK_LEFT_PCT + p * TRACK_SPAN;
          return (
            <div
              key={p}
              className="absolute top-1/2 -translate-y-1/2 w-px h-2 bg-navy-200 dark:bg-navy-600"
              style={{ left: `${left}%` }}
              aria-hidden="true"
            />
          );
        })}

        {/* Endpoint marker at 0% (start) */}
        <div
          className="absolute top-1/2 -translate-y-1/2 left-[6%] w-1 h-3 -translate-x-1/2 rounded-full bg-navy-300 dark:bg-navy-500"
          aria-hidden="true"
        />
        {/* Endpoint marker at 100% (end) */}
        <div
          className="absolute top-1/2 -translate-y-1/2 left-[90%] w-1 h-3 -translate-x-1/2 rounded-full bg-navy-300 dark:bg-navy-500"
          aria-hidden="true"
        />

        {/* Dots — positioned absolutely, centred on (left, 50%).
            CRITICAL: the OUTER wrapper owns positioning (Tailwind transform).
            The INNER motion.div owns only fade-in (opacity). If you put
            framer-motion `animate={{ y: 0 }}` on the same element that uses
            Tailwind's `-translate-y-1/2`, framer's inline `transform:
            translateY(0)` wins and the dot drops half its height below the
            baseline. Splitting the two responsibilities keeps both correct. */}
        {dots.map((d, i) => (
          <div
            key={d.key}
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
            style={{ left: `${d.left}%` }}
          >
            <motion.button
              type="button"
              initial={reduce ? false : { opacity: 0, scale: 0.6 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.32, delay: reduce ? 0 : 0.06 * i, ease: "easeOut" }}
              className="group relative block rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-navy-800 focus-visible:ring-navy-500 dark:focus-visible:ring-gold-400"
              aria-label={
                `Contradiction ${i + 1} of ${dots.length}: ${SEV_LABEL[d.severity] ?? d.severity} severity` +
                (d.ts != null ? `, at ${fmtMMSS(d.ts)}` : "") +
                `, ${Math.round(d.confidence * 100)}% confidence`
              }
              title={
                (d.ts != null ? `${fmtMMSS(d.ts)} · ` : "") +
                `${SEV_LABEL[d.severity] ?? d.severity} · ${Math.round(d.confidence * 100)}% confidence`
              }
            >
              <span
                className={`block w-3.5 h-3.5 rounded-full ring-4 ${SEV_COLORS[d.severity] ?? "bg-gray-400"} ${SEV_RING[d.severity] ?? "ring-gray-200"} transition-transform group-hover:scale-110 group-focus-visible:scale-110`}
              />
            </motion.button>
            {/* Timestamp label under each dot. Sits OUTSIDE the motion.button
                so motion animations can't shift it either. */}
            {d.ts != null && (
              <span
                className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-[calc(100%+4px)] text-[9px] font-mono text-gray-500 dark:text-gray-400 whitespace-nowrap"
                aria-hidden="true"
              >
                {fmtMMSS(d.ts)}
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Axis caption */}
      <div className="flex justify-between text-[10px] text-gray-400 dark:text-gray-500 mt-2">
        <span>start of testimony</span>
        <span>{withTs.length ? `peak @ ${fmtMMSS(maxTs)}` : "ordered by entry"}</span>
      </div>
    </div>
  );
}
