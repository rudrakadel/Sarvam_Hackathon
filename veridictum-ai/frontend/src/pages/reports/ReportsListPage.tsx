/**
 * VeriDictum AI — Reports List Page
 * Shows all generated PDF reports grouped by case.
 */

import { useQuery } from "@tanstack/react-query";
import {
  FileDown,
  Clock,
  CheckCircle,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { reportsApi, casesApi } from "@/services/api";
import type { Report, ReportStatus } from "@/types";
import { format } from "date-fns";

// ─── Status icon ─────────────────────────────────────────────────────────────

function ReportStatusIcon({ status }: { status: ReportStatus }) {
  switch (status) {
    case "COMPLETE":
      return <CheckCircle className="w-4 h-4 text-green-500" />;
    case "GENERATING":
      return <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />;
    case "FAILED":
      return <AlertCircle className="w-4 h-4 text-red-500" />;
    default:
      return <Clock className="w-4 h-4 text-gray-400" />;
  }
}

// ─── Per-case section ─────────────────────────────────────────────────────────

function CaseReportSection({ caseId, caseTitle }: { caseId: string; caseTitle: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["reports", caseId],
    queryFn: () => reportsApi.list(caseId),
  });

  const reports: Report[] = (data?.data as any)?.items ?? [];
  if (isLoading || reports.length === 0) return null;

  return (
    <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-50 dark:border-navy-700 bg-gray-50 dark:bg-navy-900/40">
        <h3 className="text-sm font-semibold text-gray-700 dark:text-gray-200">{caseTitle}</h3>
      </div>
      <div className="divide-y divide-gray-50 dark:divide-navy-700">
        {reports.map((report) => (
          <div
            key={report.id}
            className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 dark:hover:bg-navy-700/40 transition-colors"
          >
            <div className="flex items-center gap-3">
              <ReportStatusIcon status={report.status} />
              <div>
                <p className="text-sm font-medium text-gray-800 dark:text-gray-100">{report.title}</p>
                <p className="text-xs text-gray-400 dark:text-gray-500">
                  {format(new Date(report.created_at), "MMM d, yyyy 'at' HH:mm")}
                  {report.page_count ? ` · ${report.page_count} pages` : ""}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {report.status === "COMPLETE" && report.download_url && (
                <a
                  href={report.download_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-navy-600 hover:bg-navy-700 dark:bg-gold-500 dark:hover:bg-gold-600 dark:text-navy-900 text-white text-xs font-medium transition-colors"
                >
                  <FileDown className="w-3 h-3" />
                  Download PDF
                </a>
              )}
              {report.status === "FAILED" && (
                <span className="text-xs text-red-500 dark:text-red-400">Generation failed</span>
              )}
              {(report.status === "GENERATING" || report.status === "QUEUED") && (
                <span className="text-xs text-blue-600 dark:text-blue-400">Generating…</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Main page ─────────────────────────────────────────────────────────────

export function ReportsListPage() {
  const { data: casesData, isLoading } = useQuery({
    queryKey: ["cases"],
    queryFn: () => casesApi.list({ page: 1, page_size: 100 }),
  });

  const cases = (casesData?.data as any)?.items ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-navy-600 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-2">
          <FileDown className="w-6 h-6 text-navy-600 dark:text-gold-400" />
          Reports
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
          AI-generated contradiction intelligence reports. All reports are signed with an
          attorney-review disclaimer and stored as encrypted PDF.
        </p>
      </div>

      {cases.length === 0 ? (
        <div className="text-center py-20 bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm">
          <div className="w-16 h-16 rounded-full bg-gray-100 dark:bg-navy-700 flex items-center justify-center mx-auto mb-4">
            <FileDown className="w-8 h-8 text-gray-400 dark:text-gray-500" />
          </div>
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-1">No reports yet</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm mx-auto">
            Complete a case analysis to generate your first contradiction intelligence report.
            Reports are created from the case detail page.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {cases.map((c: any) => (
            <CaseReportSection key={c.id} caseId={c.id} caseTitle={c.title} />
          ))}
          {/* Contextual footer */}
          <p className="text-xs text-gray-400 dark:text-gray-500 text-center pt-2">
            Reports are generated from the case detail page after running contradiction analysis.
          </p>
        </div>
      )}
    </div>
  );
}
