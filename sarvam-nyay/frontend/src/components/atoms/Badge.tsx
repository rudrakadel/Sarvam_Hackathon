/**
 * VeriDictum AI — Badge Atom Component
 * Severity and status badges used throughout the app.
 */

import { clsx } from "clsx";
import type { ContradictionSeverity, ContradictionStatus, ProcessingStatus } from "@/types";
import { formatLabel } from "@/utils/format";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "severity" | "status" | "processing";
  severity?: ContradictionSeverity;
  className?: string;
}

const severityClasses: Record<ContradictionSeverity, string> = {
  CRITICAL: "bg-red-100 text-red-800 border-red-200",
  HIGH: "bg-orange-100 text-orange-800 border-orange-200",
  MEDIUM: "bg-yellow-100 text-yellow-800 border-yellow-200",
  LOW: "bg-blue-100 text-blue-800 border-blue-200",
  INFORMATIONAL: "bg-gray-100 text-gray-700 border-gray-200",
};

const processingClasses: Record<ProcessingStatus, string> = {
  QUEUED: "bg-gray-100 text-gray-600",
  PROCESSING: "bg-blue-100 text-blue-700",
  DIARIZATION_COMPLETE: "bg-purple-100 text-purple-700",
  TRANSCRIBING: "bg-indigo-100 text-indigo-700",
  INDEXING: "bg-cyan-100 text-cyan-700",
  COMPLETE: "bg-green-100 text-green-700",
  FAILED: "bg-red-100 text-red-700",
  RETRYING: "bg-yellow-100 text-yellow-700",
};

export function SeverityBadge({ severity }: { severity: ContradictionSeverity }) {
  const dot: Record<ContradictionSeverity, string> = {
    CRITICAL: "bg-red-500",
    HIGH: "bg-orange-500",
    MEDIUM: "bg-yellow-500",
    LOW: "bg-blue-500",
    INFORMATIONAL: "bg-gray-400",
  };
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border",
        severityClasses[severity]
      )}
    >
      <span className={clsx("w-1.5 h-1.5 rounded-full flex-shrink-0", dot[severity])} />
      {formatLabel(severity)}
    </span>
  );
}

export function ProcessingBadge({ status }: { status: ProcessingStatus }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium",
        processingClasses[status]
      )}
    >
      {status === "PROCESSING" || status === "TRANSCRIBING" ? (
        <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
      ) : null}
      {formatLabel(status)}
    </span>
  );
}

export function StatusBadge({
  status,
}: {
  status: ContradictionStatus;
}) {
  const classes: Record<ContradictionStatus, string> = {
    AI_SUGGESTED: "bg-amber-100 text-amber-800 border border-amber-300",
    CONFIRMED: "bg-green-100 text-green-700",
    REJECTED: "bg-red-100 text-red-700",
    ANNOTATED: "bg-blue-100 text-blue-700",
  };
  const labels: Record<ContradictionStatus, string> = {
    AI_SUGGESTED: "✦ AI Suggested",
    CONFIRMED: "✓ Confirmed",
    REJECTED: "✗ Rejected",
    ANNOTATED: "Annotated",
  };
  return (
    <span className={clsx("inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold", classes[status])}>
      {labels[status]}
    </span>
  );
}

export function Badge({ children, className }: BadgeProps) {
  return (
    <span className={clsx("inline-flex px-2.5 py-0.5 rounded-full text-xs font-medium bg-navy-100 text-navy-600", className)}>
      {children}
    </span>
  );
}
