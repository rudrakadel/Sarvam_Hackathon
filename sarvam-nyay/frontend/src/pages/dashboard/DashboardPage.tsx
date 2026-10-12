/**
 * VeriDictum AI — Dashboard Page
 * Real-time org-level stats from /api/v1/dashboard.
 */

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Briefcase,
  AlertTriangle,
  FileText,
  Mic,
  Plus,
  Loader2,
  CheckCircle2,
} from "lucide-react";
import { casesApi, dashboardApi } from "@/services/api";
import { useAuthStore } from "@/store/authStore";
import { Button } from "@/components/atoms/Button";
import { Skeleton } from "@/components/atoms/Skeleton";
import { SeverityDonut } from "@/components/organisms/SeverityDonut";
import { formatLabel } from "@/utils/format";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import { motion } from "framer-motion";
import type { Case, DashboardStats } from "@/types";

const SEVERITY_COLORS: Record<string, string> = {
  CRITICAL: "bg-red-500",
  HIGH: "bg-orange-500",
  MEDIUM: "bg-amber-400",
  LOW: "bg-blue-400",
};

function StatCard({
  title,
  value,
  icon: Icon,
  color,
  href,
  loading,
  severityBreakdown,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  href?: string;
  loading?: boolean;
  severityBreakdown?: Record<string, number>;
}) {
  // Build the severity stack chips, dropping zero-count buckets so non-zero
  // severities draw the eye. The Contradictions tile is the only consumer.
  const sevEntries = severityBreakdown
    ? (["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const)
        .map((k) => [k, severityBreakdown[k] ?? 0] as const)
        .filter(([, n]) => n > 0)
    : [];

  const content = (
    <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-[0_1px_3px_rgba(0,0,0,0.08)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.3)] p-6 flex items-center gap-4 hover:shadow-md transition-shadow">
      <div className={`flex items-center justify-center w-12 h-12 rounded-xl flex-shrink-0 ${color}`}>
        <Icon className="w-6 h-6 text-white" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">{title}</p>
        {loading ? (
          <Skeleton className="w-16 h-7" />
        ) : (
          <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
        )}
        {sevEntries.length > 0 && !loading && (
          <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5">
            {sevEntries.map(([sev, n]) => (
              <div key={sev} className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${SEVERITY_COLORS[sev]}`} />
                <span className="text-[11px] font-medium text-gray-600 dark:text-gray-400">
                  {n} {sev.toLowerCase()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
  return href ? <Link to={href}>{content}</Link> : content;
}

function QueueBadge({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
      <Loader2 className="w-3 h-3 animate-spin" />
      {count} processing
    </span>
  );
}

export function DashboardPage() {
  const { user } = useAuthStore();

  const { data: dashData, isLoading: dashLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboardApi.get(),
    refetchInterval: 30_000,
  });

  const { data: casesData } = useQuery({
    queryKey: ["cases", "recent"],
    queryFn: () => casesApi.list({ page: 1, page_size: 5 }),
  });

  const stats: DashboardStats | undefined = dashData?.data;
  const recentCases: Case[] = casesData?.data?.items || [];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Welcome back, {(() => {
              const name = user?.full_name ?? "";
              const stripped = name.replace(/,?\s*(Esq\.|J\.D\.|Esq|JD|Atty\.|Attorney)\.?$/i, "").trim();
              const first = stripped.split(" ")[0];
              return first && first.length > 1 ? first : stripped || "Counselor";
            })()}
          </h1>
          <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">Sarvam Nyaya overview</p>
        </div>
        <Link to="/cases/new">
          <Button>
            <Plus className="w-4 h-4" />
            New Case
          </Button>
        </Link>
      </div>

      {/* Stats — staggered entry */}
      <StatGrid
        cards={[
          { title: "Total Cases",         value: stats?.cases.total ?? 0,           icon: Briefcase,    color: "bg-navy-600",   href: "/cases" },
          { title: "Contradictions Found", value: stats?.contradictions.total ?? 0, icon: AlertTriangle, color: "bg-red-500",   severityBreakdown: stats?.contradictions.by_severity },
          { title: "Documents",            value: stats?.evidence.total_documents ?? 0, icon: FileText,  color: "bg-blue-500" },
          { title: "Audio Files",          value: stats?.evidence.total_audio ?? 0,  icon: Mic,         color: "bg-purple-500" },
        ]}
        loading={dashLoading}
      />


      {/* Premium hero strip — AI-look donut + Vera's top find */}
      {stats && stats.contradictions.total > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1 relative overflow-hidden rounded-xl border border-navy-100/60 dark:border-navy-700 bg-white dark:bg-navy-800 p-5 shadow-sm">
            <div className="absolute inset-0 bg-gradient-to-br from-gold-50/60 via-white to-white dark:from-gold-500/10 dark:via-navy-800 dark:to-navy-800 pointer-events-none" />
            <div className="relative">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-700 dark:text-gold-300 mb-3">
                Contradictions by severity
              </p>
              <SeverityDonut
                by_severity={stats.contradictions.by_severity}
                total={stats.contradictions.total}
              />
            </div>
          </div>
          <div className="lg:col-span-2 relative overflow-hidden rounded-xl border border-navy-100/60 dark:border-navy-700 bg-gradient-to-br from-navy-50 via-white to-gold-50/40 dark:from-navy-800 dark:via-navy-800 dark:to-gold-500/10 p-5 shadow-sm">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-navy-700 dark:text-gold-300 mb-1.5">
              Vera's top finding
            </p>
            <p className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed">
              {stats.contradictions.critical > 0 ? (
                <>
                  <strong className="text-red-700 dark:text-red-400">
                    {stats.contradictions.critical} critical contradiction
                    {stats.contradictions.critical === 1 ? "" : "s"}
                  </strong>{" "}
                  detected across your caseload — each pairs a transcript
                  statement against a documentary record. Click into a case to
                  review side-by-side.
                </>
              ) : (
                <>
                  No critical contradictions outstanding. Run analysis on a
                  new case to surface high-severity conflicts.
                </>
              )}
            </p>
            <div className="mt-3 flex items-center gap-2 text-[11px] text-navy-600 dark:text-gray-400">
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-white/70 dark:bg-navy-900/60 border border-navy-100 dark:border-navy-700">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 motion-safe:animate-breath" />
                live
              </span>
              <span>updated every 30 s</span>
            </div>
          </div>
        </div>
      )}

      {/* Loading skeleton — only while the first dashboard fetch is in flight */}
      {dashLoading && !stats && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Skeleton className="h-36 lg:col-span-1" />
          <Skeleton className="h-36 lg:col-span-2" />
        </div>
      )}

      {/* Critical alert */}
      {stats && stats.contradictions.critical > 0 && (
        <div className="bg-red-50 dark:bg-red-500/10 border border-red-200 dark:border-red-500/30 rounded-xl p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-300">
              {stats.contradictions.critical} critical contradiction
              {stats.contradictions.critical > 1 ? "s" : ""} detected
            </p>
            <p className="text-xs text-red-700 dark:text-red-300/80 mt-0.5">
              {stats.contradictions.pending_review} pending attorney review.
            </p>
          </div>
        </div>
      )}

      {/* AI disclaimer */}
      <div className="bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 rounded-xl p-4 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-medium text-amber-800 dark:text-amber-300">Attorney Review Required</p>
          <p className="text-xs text-amber-700 dark:text-amber-300/80 mt-0.5">
            All AI-detected contradictions are suggestions only and must be reviewed by a licensed attorney before use in legal proceedings.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Cases */}
        <div className="lg:col-span-2 bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 dark:border-navy-700">
            <h2 className="font-semibold text-gray-900 dark:text-gray-100">Recent Cases</h2>
            <Link to="/cases" className="text-sm text-navy-600 dark:text-gold-400 hover:underline">
              View all
            </Link>
          </div>
          <div className="divide-y divide-gray-50 dark:divide-navy-700">
            {recentCases.length === 0 ? (
              <div className="px-6 py-12 text-center">
                <Briefcase className="w-12 h-12 text-gray-300 dark:text-navy-600 mx-auto mb-3" />
                <p className="text-gray-500 dark:text-gray-400 text-sm">No cases yet.</p>
                <Link to="/cases/new">
                  <Button variant="outline" size="sm" className="mt-3">
                    <Plus className="w-4 h-4" />
                    Create First Case
                  </Button>
                </Link>
              </div>
            ) : (
              recentCases.map((c) => (
                <Link
                  key={c.id}
                  to={`/cases/${c.id}`}
                  className="flex items-center justify-between px-6 py-4 hover:bg-gray-50 dark:hover:bg-navy-700/40 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{c.title}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                      {c.case_number} · {formatLabel(c.case_type)}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                      c.status === "OPEN"
                        ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400"
                        : c.status === "IN_REVIEW"
                        ? "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400"
                        : "bg-gray-100 text-gray-600 dark:bg-navy-700 dark:text-gray-400"
                    }`}
                  >
                    {formatLabel(c.status)}
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Processing queue */}
          <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 text-sm">Processing Queue</h3>
            {dashLoading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-6 bg-gray-100 animate-pulse rounded" />
                ))}
              </div>
            ) : (stats?.evidence.total_in_queue ?? 0) === 0 ? (
              <div className="flex items-center gap-2 py-2">
                <CheckCircle2 className="w-4 h-4 text-gray-300 dark:text-navy-600 flex-shrink-0" />
                <p className="text-xs text-gray-400 dark:text-gray-500">No active jobs — queue is empty</p>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-300">Audio transcription</span>
                  <QueueBadge count={stats?.evidence.audio_in_queue ?? 0} />
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-600 dark:text-gray-300">Document OCR</span>
                  <QueueBadge count={stats?.evidence.documents_in_queue ?? 0} />
                </div>
              </div>
            )}
          </div>

          {/* Contradiction review summary */}
          <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 text-sm">Review Status</h3>
            {dashLoading ? (
              <Skeleton className="h-16" />
            ) : (
              <div className="space-y-2">
                {Object.entries(stats?.contradictions.by_status ?? {}).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-300">{formatLabel(k)}</span>
                    <span className="font-semibold text-gray-900 dark:text-gray-100">{v as number}</span>
                  </div>
                ))}
                {!stats?.contradictions.total && (
                  <p className="text-xs text-gray-400 dark:text-gray-500">No contradictions yet.</p>
                )}
              </div>
            )}
          </div>

          {/* Reports */}
          <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm p-5">
            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-3 text-sm">Reports</h3>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-600 dark:text-gray-300">Generated</span>
              <span className="font-semibold text-gray-900 dark:text-gray-100">
                {stats?.reports.complete ?? 0}
              </span>
            </div>
            <div className="flex items-center justify-between text-sm mt-2">
              <span className="text-gray-600 dark:text-gray-300">Total</span>
              <span className="font-semibold text-gray-900 dark:text-gray-100">
                {stats?.reports.total ?? 0}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ───── Helpers ────────────────────────────────────────────────────────────

interface StatGridCard {
  title: string;
  value: string | number;
  icon: React.ElementType;
  color: string;
  href?: string;
  severityBreakdown?: Record<string, number>;
}

interface StatGridProps {
  cards: StatGridCard[];
  loading: boolean;
}

function StatGrid({ cards, loading }: StatGridProps) {
  const reduce = useReducedMotion();
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((c, i) => (
        <motion.div
          key={c.title}
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, delay: reduce ? 0 : 0.04 * i, ease: "easeOut" }}
        >
          <StatCard {...c} loading={loading} />
        </motion.div>
      ))}
    </div>
  );
}
