/**
 * VeriDictum AI — Case Detail Page
 * Tabs: Overview | Audio | Documents | Contradictions | Ask AI | Reports
 */

import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Mic, FileText, AlertTriangle, MessageSquare, BarChart3,
  Info, Upload, Zap, Download, CheckCircle, XCircle,
  Loader2, RefreshCw, Brain, FolderOpen, ArrowLeft, ChevronRight,
  MoreHorizontal,
} from "lucide-react";
import toast from "react-hot-toast";
import { casesApi, contradictionsApi, reportsApi, audioApi, documentsApi, courtroomApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { SeverityBadge, StatusBadge } from "@/components/atoms/Badge";
import { ContradictionTimeline } from "@/components/organisms/ContradictionTimeline";
import type { AudioFile, Case, Contradiction, Document, Report } from "@/types";
import { format } from "date-fns";
import { formatLabel, formatTimestamp } from "@/utils/format";
import { useCaseEvents } from "@/hooks/useWebSocket";
import { motion } from "framer-motion";
import { useReducedMotion } from "@/hooks/useReducedMotion";

type Tab = "overview" | "audio" | "documents" | "contradictions" | "query" | "reports";

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function ProcessingChip({ status }: { status: string }) {
  const isActive = status === "PROCESSING" || status === "QUEUED" || status === "TRANSCRIBING";
  return (
    <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
      status === "COMPLETE" ? "bg-green-100 text-green-700"
      : status === "FAILED" ? "bg-red-100 text-red-700"
      : "bg-amber-100 text-amber-700"
    }`}>
      {isActive && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
      {formatLabel(status)}
    </span>
  );
}

/** Animated thinking indicator shown while AI is running */
function AnalysisProgress() {
  const steps = [
    "Transcribing audio segments",
    "Extracting document text",
    "Running contradiction analysis",
    "Finalizing results",
  ];
  return (
    <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-3">
        <Brain className="w-5 h-5 text-blue-600 flex-shrink-0" />
        <p className="text-sm font-semibold text-blue-800">AI analysis in progress…</p>
        <div className="flex items-center gap-1 ml-auto">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-2 h-2 bg-blue-500 rounded-full animate-bounce"
              style={{ animationDelay: `${i * 0.15}s` }}
            />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <div key={step} className="flex items-center gap-3">
            <div className={`w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 ${
              i === 0 ? "bg-blue-500" : "bg-blue-200"
            }`}>
              {i === 0 ? (
                <Loader2 className="w-3 h-3 text-white animate-spin" />
              ) : (
                <span className="w-2 h-2 rounded-full bg-blue-400" />
              )}
            </div>
            <span className={`text-xs ${i === 0 ? "text-blue-800 font-medium" : "text-blue-400"}`}>
              {step}
            </span>
          </div>
        ))}
      </div>
      <p className="text-xs text-blue-600">Approx. 30–60 seconds</p>
    </div>
  );
}

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [reviewNotes, setReviewNotes] = useState("");
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [courtroomAudit, setCourtroomAudit] = useState<any | null>(null);
  const [moreMenuOpen, setMoreMenuOpen] = useState(false);
  const queryClient = useQueryClient();

  const { data: caseData, isLoading } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
  });

  // Real-time WebSocket events — auto-invalidates queries on transcript/OCR/analysis completion
  useCaseEvents(caseId);

  // Eager fetch — the Overview tab's timeline strip needs this regardless of
  // which tab is active.
  const { data: contradictionsData } = useQuery({
    queryKey: ["contradictions", caseId],
    queryFn: () => contradictionsApi.list(caseId!, { page: 1, page_size: 50 }),
    enabled: !!caseId,
  });

  // Phase E — persisted voice transcripts for this case (shown on Overview)
  const { data: voiceRecordsData } = useQuery({
    queryKey: ["voice-records", caseId],
    queryFn: () => courtroomApi.voiceRecords(caseId!),
    enabled: !!caseId,
  });
  const voiceRecords: Array<{
    id: string;
    voice_transcript: string;
    transcript_status: string;
    provider: string | null;
    language: string | null;
    word_count: number | null;
    original_filename: string | null;
    created_at: string | null;
  }> = voiceRecordsData?.data || [];

  const { data: statsData } = useQuery({
    queryKey: ["contradiction-stats", caseId],
    queryFn: () => contradictionsApi.stats(caseId!),
    enabled: !!caseId,
  });

  // Audio + documents are fetched eagerly so the Overview AI Case Summary tile
  // always has accurate counts. The tabs themselves still only mount when active.
  const { data: audioData, isLoading: audioLoading } = useQuery({
    queryKey: ["audio", caseId],
    queryFn: () => audioApi.list(caseId!),
    enabled: !!caseId,
  });

  const { data: documentsData, isLoading: documentsLoading } = useQuery({
    queryKey: ["documents", caseId],
    queryFn: () => documentsApi.list(caseId!),
    enabled: !!caseId,
  });

  const { data: reportsData, isLoading: reportsLoading } = useQuery({
    queryKey: ["reports-case", caseId],
    queryFn: () => reportsApi.list(caseId!),
    enabled: activeTab === "reports",
  });

  const analysisMutation = useMutation({
    mutationFn: () => contradictionsApi.analyze(caseId!),
    onMutate: () => setAnalysisRunning(true),
    onSuccess: (res: any) => {
      queryClient.invalidateQueries({ queryKey: ["contradictions", caseId] });
      queryClient.invalidateQueries({ queryKey: ["contradiction-stats", caseId] });
      setAnalysisRunning(false);
      const found = res?.data?.contradictions_found ?? res?.data?.count;
      toast.success(
        found != null
          ? `Analysis complete — ${found} contradiction${found !== 1 ? "s" : ""} found.`
          : "Analysis complete."
      );
    },
    onError: () => {
      setAnalysisRunning(false);
      toast.error("Analysis failed. Please try again.");
    },
  });

  const reportMutation = useMutation({
    mutationFn: () => reportsApi.create(caseId!, {
      title: `Contradiction Report — ${kase?.title ?? caseId}`,
      include_contradictions: true,
      include_transcript_excerpts: true,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reports-case", caseId] });
      toast.success("Report generation started. You'll be notified when ready.");
    },
    onError: () => toast.error("Failed to generate report."),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: string; notes: string }) =>
      contradictionsApi.review(caseId!, id, { status, attorney_notes: notes }),
    onSuccess: (_res, vars) => {
      queryClient.invalidateQueries({ queryKey: ["contradictions", caseId] });
      queryClient.invalidateQueries({ queryKey: ["contradiction-stats", caseId] });
      setReviewingId(null);
      setReviewNotes("");
      toast.success(vars.status === "CONFIRMED" ? "Contradiction confirmed." : "Contradiction rejected.");
    },
    onError: () => toast.error("Failed to save review. Please try again."),
  });

  const retranscribeMutation = useMutation({
    mutationFn: (audioId: string) => audioApi.retranscribe(caseId!, audioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["audio", caseId] });
      toast.success("Re-transcription queued.");
    },
    onError: () => toast.error("Failed to queue re-transcription."),
  });

  const courtroomAuditMutation = useMutation({
    mutationFn: () => courtroomApi.audit(caseId!),
    onSuccess: (res: any) => {
      const data = res?.data || {};
      setCourtroomAudit(data);
      setActiveTab("overview");
      const matrix = data.matrix || {};
      const confirmed = matrix.confirmed_critical ?? 0;
      const gaps = (data.evidence_gaps || []).length;
      toast.success(
        `Courtroom audit complete — ${data.contradictions_checked ?? 0} contradictions, ` +
        `${confirmed} confirmed critical, ${gaps} evidence gap${gaps !== 1 ? "s" : ""}.`
      );
    },
    onError: () => toast.error("Courtroom audit failed. Please try again."),
  });

  const courtroomBriefMutation = useMutation({
    mutationFn: () => courtroomApi.brief(caseId!),
    onSuccess: (res: any) => {
      const blob = new Blob([res.data], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `courtroom-brief-${caseId}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Courtroom brief PDF downloaded.");
    },
    onError: () => toast.error("Failed to download courtroom brief PDF."),
  });

  const deleteDocMutation = useMutation({
    mutationFn: (docId: string) => documentsApi.delete(caseId!, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", caseId] });
      toast.success("Document removed from case.");
    },
    onError: () => toast.error("Failed to delete document."),
  });

  const kase: Case | undefined = caseData?.data;
  const contradictions: Contradiction[] = contradictionsData?.data?.items || [];
  const stats = statsData?.data;
  const audioFiles: AudioFile[] = audioData?.data || [];
  const documents: Document[] = documentsData?.data || [];
  const reports: Report[] = (reportsData?.data as any)?.items || [];

  const tabs = [
    { id: "overview", label: "Overview", icon: Info },
    { id: "audio", label: "Audio", icon: Mic },
    { id: "documents", label: "Documents", icon: FileText },
    { id: "contradictions", label: `Contradictions${stats?.total ? ` (${stats.total})` : ""}`, icon: AlertTriangle },
    { id: "query", label: "Ask AI", icon: MessageSquare },
    { id: "reports", label: "Reports", icon: BarChart3 },
  ] as const;

  if (isLoading) return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-8 h-8 border-navy-600 animate-spin" />
    </div>
  );

  if (!kase) {
    return (
      <div className="max-w-2xl mx-auto py-20 text-center px-6">
        <div className="w-20 h-20 rounded-full bg-gray-100 flex items-center justify-center mx-auto mb-5">
          <FolderOpen className="w-10 h-10 text-gray-400" />
        </div>
        <h2 className="text-xl font-bold text-gray-900 mb-2">Case Not Found</h2>
        <p className="text-gray-500 text-sm mb-6 max-w-sm mx-auto">
          This case doesn't exist or you may not have permission to access it. It may have been
          archived or the link may be outdated.
        </p>
        <Link to="/cases">
          <Button>
            <ArrowLeft className="w-4 h-4" />
            Back to Cases
          </Button>
        </Link>
      </div>
    );
  }

  const TAB_LABELS: Record<Tab, string> = {
    overview: "Overview",
    audio: "Audio",
    documents: "Documents",
    contradictions: "Contradictions",
    query: "Ask AI",
    reports: "Reports",
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400" aria-label="Breadcrumb">
        <Link to="/cases" className="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">Cases</Link>
        <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        <span className="text-gray-900 dark:text-gray-100 font-medium truncate max-w-[240px]">{kase.title}</span>
        {activeTab !== "overview" && (
          <>
            <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="text-gray-900 dark:text-gray-100 font-medium">{TAB_LABELS[activeTab]}</span>
          </>
        )}
      </nav>

      {/* Header */}
      <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="text-xs font-mono bg-navy-50 text-navy-600 dark:bg-navy-700 dark:text-gold-300 px-2 py-1 rounded">{kase.case_number}</span>
              <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                kase.status === "OPEN" ? "bg-green-100 text-green-700 dark:bg-green-500/15 dark:text-green-400"
                : kase.status === "IN_REVIEW" ? "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400"
                : "bg-gray-100 text-gray-600 dark:bg-navy-700 dark:text-gray-300"
              }`}>{formatLabel(kase.status)}</span>
            </div>
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">{kase.title}</h1>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {formatLabel(kase.case_type)}
              {kase.court ? ` · ${kase.court}` : ""}
              {kase.jurisdiction ? ` · ${kase.jurisdiction}` : ""}
            </p>
          </div>

          <div className="flex gap-2 flex-wrap justify-end items-start">
            {/* Primary CTA — Run Analysis is the differentiating action and
                should dominate. Secondary action — Generate Report — is the
                expected next step once analysis runs. */}
            <Button
              size="sm"
              onClick={() => {
                analysisMutation.mutate();
                setActiveTab("overview");
              }}
              loading={analysisMutation.isPending}
              className="shadow-sm"
            >
              <Zap className="w-4 h-4" />
              {analysisMutation.isPending ? "Analyzing…" : "Run Analysis"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setActiveTab("reports");
                reportMutation.mutate();
              }}
              loading={reportMutation.isPending}
            >
              <Download className="w-4 h-4" />
              Generate Report
            </Button>
            {/* Tertiary tools collapsed into a More dropdown to remove the
                four-equal-buttons confusion. */}
            <div className="relative" data-more-menu>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setMoreMenuOpen((v) => !v)}
                title="More tools"
                aria-haspopup="menu"
                aria-expanded={moreMenuOpen}
              >
                <MoreHorizontal className="w-4 h-4" />
                More
              </Button>
              {moreMenuOpen && (
                <div
                  className="absolute right-0 mt-1 z-10 w-60 rounded-lg border border-gray-100 bg-white shadow-lg py-1 text-sm"
                  role="menu"
                  onMouseLeave={() => setMoreMenuOpen(false)}
                >
                  <button
                    className="flex items-center gap-2 w-full px-3 py-2 hover:bg-gray-50 text-gray-700 disabled:opacity-50"
                    role="menuitem"
                    disabled={courtroomAuditMutation.isPending}
                    onClick={() => { setMoreMenuOpen(false); courtroomAuditMutation.mutate(); }}
                  >
                    <Mic className="w-4 h-4 text-navy-600" />
                    {courtroomAuditMutation.isPending ? "Auditing…" : "Run Courtroom Audit"}
                  </button>
                  <button
                    className="flex items-center gap-2 w-full px-3 py-2 hover:bg-gray-50 text-gray-700 disabled:opacity-50"
                    role="menuitem"
                    disabled={courtroomBriefMutation.isPending}
                    onClick={() => { setMoreMenuOpen(false); courtroomBriefMutation.mutate(); }}
                  >
                    <FileText className="w-4 h-4 text-navy-600" />
                    {courtroomBriefMutation.isPending ? "Preparing…" : "Download Courtroom Brief PDF"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Contradiction severity summary — hide zero-count pills so the
            non-zero severities pop. Pending-review badge mirrors the count
            (green dot + "All reviewed" when zero). */}
        {stats && stats.total > 0 && (
          <div className="flex flex-wrap gap-x-6 gap-y-2 mt-4 pt-4 border-t border-gray-100 dark:border-navy-700">
            {(["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const).map((sev) => {
              const count = (stats.by_severity as Record<string, number>)?.[sev] ?? 0;
              if (count === 0) return null;
              return (
                <div key={sev} className="flex items-center gap-2">
                  <SeverityBadge severity={sev} />
                  <span className="font-semibold text-gray-900 dark:text-gray-100">{count}</span>
                </div>
              );
            })}
            <div className="ml-auto flex items-center gap-1.5 text-xs">
              {(stats.pending_review ?? 0) > 0 ? (
                <>
                  <span className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-amber-700 dark:text-amber-400 font-medium">
                    {stats.pending_review} pending attorney review
                  </span>
                </>
              ) : (
                <>
                  <span className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-green-700 dark:text-green-400">All contradictions reviewed</span>
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm overflow-hidden">
        <div className="flex border-b border-gray-100 dark:border-navy-700 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as Tab)}
              className={`flex items-center gap-2 px-5 py-3.5 text-sm font-medium whitespace-nowrap transition-colors border-b-2 -mb-px ${
                activeTab === tab.id
                  ? "border-navy-600 dark:border-gold-400 text-navy-600 dark:text-gold-400"
                  : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
              }`}
            >
              <tab.icon className="w-4 h-4" />
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {/* ── Overview ── */}
          {activeTab === "overview" && (
            <div className="space-y-6">
              {/* Analysis progress state */}
              {analysisRunning && <AnalysisProgress />}

              {/* Phase D — Courtroom Audit result strip */}
              {courtroomAudit && (
                <div className="bg-white border border-navy-100 rounded-xl p-5">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center gap-2">
                      <Mic className="w-4 h-4 text-navy-600" />
                      <p className="text-sm font-semibold text-navy-800">
                        Courtroom Audit
                        <span className="ml-2 text-xs font-normal text-gray-500">
                          mode: {courtroomAudit.mode || "n/a"}
                        </span>
                      </p>
                    </div>
                    <button
                      onClick={() => courtroomBriefMutation.mutate()}
                      disabled={courtroomBriefMutation.isPending}
                      className="text-xs text-navy-600 hover:text-navy-800 underline disabled:opacity-50"
                    >
                      {courtroomBriefMutation.isPending ? "Preparing…" : "Download PDF brief"}
                    </button>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    <div className="bg-gray-50 rounded-lg p-3">
                      <p className="text-xs text-gray-500">Contradictions</p>
                      <p className="text-xl font-bold text-gray-900">
                        {courtroomAudit.contradictions_checked ?? 0}
                      </p>
                    </div>
                    <div className="bg-red-50 rounded-lg p-3">
                      <p className="text-xs text-red-600">Confirmed Critical</p>
                      <p className="text-xl font-bold text-red-700">
                        {courtroomAudit.matrix?.confirmed_critical ?? 0}
                      </p>
                    </div>
                    <div className="bg-amber-50 rounded-lg p-3">
                      <p className="text-xs text-amber-700">Evidence Gaps</p>
                      <p className="text-xl font-bold text-amber-800">
                        {(courtroomAudit.evidence_gaps || []).length}
                      </p>
                    </div>
                    <div className="bg-orange-50 rounded-lg p-3">
                      <p className="text-xs text-orange-700">Low-Confidence Critical</p>
                      <p className="text-xl font-bold text-orange-800">
                        {(courtroomAudit.low_confidence_critical || []).length}
                      </p>
                    </div>
                  </div>
                  {Array.isArray(courtroomAudit.talking_points) && courtroomAudit.talking_points.length > 0 && (
                    <div className="mt-3 text-xs text-gray-600">
                      <span className="font-medium">Talking points:</span> {courtroomAudit.talking_points.length}
                    </div>
                  )}
                </div>
              )}

              {/* Phase E — Voice Transcript Viewer */}
              {voiceRecords.length > 0 && (
                <div className="bg-white dark:bg-navy-800 border border-navy-100 dark:border-navy-700 rounded-xl p-5">
                  <div className="flex items-center gap-2 mb-3">
                    <Mic className="w-4 h-4 text-navy-600 dark:text-gold-400" />
                    <p className="text-sm font-semibold text-navy-800 dark:text-gray-100">🎙️ Voice Transcript</p>
                    <span className="ml-2 text-xs text-gray-500 dark:text-gray-400">
                      {voiceRecords.length} record{voiceRecords.length !== 1 ? "s" : ""}
                    </span>
                  </div>
                  <div className="space-y-4">
                    {voiceRecords.slice(0, 1).map((rec) => (
                      <div key={rec.id} className="border border-gray-100 dark:border-navy-700 rounded-lg p-4 bg-gray-50 dark:bg-navy-900/40">
                        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400 mb-2">
                          {rec.original_filename && (
                            <span className="font-medium text-gray-700 dark:text-gray-200">{rec.original_filename}</span>
                          )}
                          {rec.provider && <span>provider: {rec.provider}</span>}
                          {rec.language && <span>lang: {rec.language.toUpperCase()}</span>}
                          {rec.word_count != null && <span>{rec.word_count} words</span>}
                          <span className="ml-auto">
                            status: <span className="font-medium text-gray-700 dark:text-gray-200">{rec.transcript_status}</span>
                            {rec.created_at && (
                              <> · {format(new Date(rec.created_at), "MMM d, yyyy HH:mm")}</>
                            )}
                          </span>
                        </div>
                        {rec.voice_transcript ? (
                          <pre className="whitespace-pre-wrap text-sm text-gray-800 dark:text-gray-200 font-sans leading-relaxed max-h-80 overflow-y-auto">
                            {rec.voice_transcript}
                          </pre>
                        ) : (
                          <p className="text-xs italic text-gray-400 dark:text-gray-500">
                            Transcript not yet available — transcription may still be in progress.
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* AI Case Summary panel — "glass" treatment: backdrop blur,
                  gold accent rim, subtle gradient. Sits as the hero of the
                  Overview tab when contradictions exist. */}
              {stats && stats.total > 0 && !analysisRunning && (
                <div className="relative overflow-hidden rounded-xl border border-gold-200/40 dark:border-gold-500/30 shadow-glow">
                  <div className="absolute inset-0 bg-gradient-to-br from-navy-50 via-white/60 to-gold-50/40 dark:from-navy-700 dark:via-navy-800 dark:to-gold-500/10 backdrop-blur" />
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold-400/60 to-transparent" />
                  <div className="relative p-5">
                  <div className="flex items-center gap-2 mb-2">
                    <Brain className="w-4 h-4 text-gold-600 dark:text-gold-400" />
                    <p className="text-sm font-semibold text-navy-800 dark:text-gray-100">AI Case Summary</p>
                    <span className="ml-1 inline-flex items-center gap-1 text-[10px] uppercase tracking-wide text-gold-700 dark:text-gold-300 bg-gold-50 dark:bg-gold-500/15 px-1.5 py-0.5 rounded-full border border-gold-200/60 dark:border-gold-500/30">
                      <span className="w-1 h-1 rounded-full bg-gold-500 motion-safe:animate-breath" />
                      Vera
                    </span>
                  </div>
                  <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
                    This is a <strong>{formatLabel(kase.case_type).toLowerCase()}</strong> case with{" "}
                    <strong>{stats.total} contradiction{stats.total !== 1 ? "s" : ""}</strong> detected
                    in the evidence.{" "}
                    {(stats.by_severity as any)?.CRITICAL > 0 && (
                      <>
                        <strong className="text-red-700 dark:text-red-400">
                          {(stats.by_severity as any).CRITICAL} critical discrepanc
                          {(stats.by_severity as any).CRITICAL === 1 ? "y" : "ies"}
                        </strong>{" "}
                        {(stats.by_severity as any).CRITICAL === 1 ? "requires" : "require"}{" "}
                        immediate attorney review.{" "}
                      </>
                    )}
                    {stats.pending_review > 0 && (
                      <>{stats.pending_review} contradiction{stats.pending_review !== 1 ? "s" : ""} are pending attorney review.</>
                    )}
                  </p>
                  <div className="flex gap-4 mt-3 text-xs text-navy-600 dark:text-gray-300">
                    <span>Confidence: {stats.avg_confidence ? `${Math.round(stats.avg_confidence * 100)}%` : "N/A"}</span>
                    <span>·</span>
                    <span>{audioFiles.length || 0} audio file{audioFiles.length !== 1 ? "s" : ""}</span>
                    <span>·</span>
                    <span>{documents.length || 0} document{documents.length !== 1 ? "s" : ""}</span>
                  </div>

                  {/* Contradiction timeline — placed inside the glass tile so it
                      reads as a part of Vera's summary, not a sibling. */}
                  {contradictions.length > 0 && (
                    <div className="mt-4">
                      <ContradictionTimeline contradictions={contradictions} />
                    </div>
                  )}
                  </div>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">Case Details</h3>
                  <dl className="space-y-2">
                    {[
                      ["Case Number", kase.case_number],
                      ["Court", kase.court || <span className="text-amber-600 dark:text-amber-400 text-xs">Not specified</span>],
                      ["Jurisdiction", kase.jurisdiction || <span className="text-amber-600 dark:text-amber-400 text-xs">Not specified</span>],
                      ["Case Type", formatLabel(kase.case_type)],
                      ["Status", formatLabel(kase.status)],
                      ["Created", format(new Date(kase.created_at), "MMM d, yyyy")],
                    ].map(([label, value]) => (
                      <div key={String(label)} className="flex gap-4">
                        <dt className="text-sm text-gray-500 dark:text-gray-400 w-32 flex-shrink-0">{label}</dt>
                        <dd className="text-sm text-gray-900 dark:text-gray-200">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </div>

                {/* Quick actions */}
                <div>
                  <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">Quick Actions</h3>
                  <div className="space-y-2">
                    <Link to={`/cases/${caseId}/upload-audio`} className="block">
                      <Button variant="outline" size="sm" className="w-full justify-start">
                        <Mic className="w-4 h-4" /> Upload Audio Evidence
                      </Button>
                    </Link>
                    <Link to={`/cases/${caseId}/upload-document`} className="block">
                      <Button variant="outline" size="sm" className="w-full justify-start">
                        <FileText className="w-4 h-4" /> Upload Document
                      </Button>
                    </Link>
                    <Button
                      variant="outline"
                      size="sm"
                      className="w-full justify-start"
                      onClick={() => { analysisMutation.mutate(); }}
                      loading={analysisMutation.isPending}
                    >
                      <Zap className="w-4 h-4" /> Run Contradiction Analysis
                    </Button>
                    <Link to={`/cases/${caseId}/query`} className="block">
                      <Button variant="outline" size="sm" className="w-full justify-start">
                        <MessageSquare className="w-4 h-4" /> Ask AI about this case
                      </Button>
                    </Link>
                  </div>

                  {kase.parties && Object.keys(kase.parties).length > 0 && (
                    <div className="mt-5">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-3">Parties</h3>
                      <dl className="space-y-2">
                        {Object.entries(kase.parties).map(([role, name]) => (
                          <div key={role} className="flex gap-4">
                            <dt className="text-sm text-gray-500 dark:text-gray-400 capitalize w-32">{role}</dt>
                            <dd className="text-sm text-gray-900 dark:text-gray-200">{name as string}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* ── Audio ── */}
          {activeTab === "audio" && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="font-medium text-gray-900">Audio Recordings</h3>
                <Link to={`/cases/${caseId}/upload-audio`}>
                  <Button size="sm"><Upload className="w-4 h-4" /> Upload Audio</Button>
                </Link>
              </div>

              {audioLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1,2,3].map(i => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}
                </div>
              ) : audioFiles.length === 0 ? (
                <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
                  <Mic className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500 text-sm">No audio recordings yet.</p>
                  <Link to={`/cases/${caseId}/upload-audio`} className="mt-3 inline-block">
                    <Button size="sm" variant="outline"><Upload className="w-4 h-4" /> Upload First Recording</Button>
                  </Link>
                </div>
              ) : (
                <div className="divide-y divide-gray-50 border border-gray-100 rounded-xl overflow-hidden">
                  {audioFiles.map((af) => (
                    <div key={af.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50">
                      <div className="flex items-center gap-3">
                        <Mic className="w-4 h-4 text-gray-400" />
                        <div>
                          <p className="text-sm font-medium text-gray-800">{af.original_filename}</p>
                          <p className="text-xs text-gray-500">
                            {formatBytes(af.file_size_bytes)}
                            {af.duration_seconds ? ` · ${Math.round(af.duration_seconds / 60)} min` : ""}
                            {af.language_hint ? ` · ${af.language_hint.toUpperCase()}` : ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <ProcessingChip status={af.status} />
                        {af.status === "COMPLETE" && (
                          <Button
                            size="sm"
                            variant="ghost"
                            loading={retranscribeMutation.isPending}
                            onClick={() => retranscribeMutation.mutate(af.id)}
                            title="Re-run transcription"
                          >
                            <RefreshCw className="w-3 h-3" /> Re-transcribe
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Documents ── */}
          {activeTab === "documents" && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="font-medium text-gray-900">Case Documents</h3>
                <Link to={`/cases/${caseId}/upload-document`}>
                  <Button size="sm"><Upload className="w-4 h-4" /> Upload Document</Button>
                </Link>
              </div>

              {documentsLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1,2,3].map(i => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}
                </div>
              ) : documents.length === 0 ? (
                <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
                  <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500 text-sm">No documents uploaded yet.</p>
                  <Link to={`/cases/${caseId}/upload-document`} className="mt-3 inline-block">
                    <Button size="sm" variant="outline"><Upload className="w-4 h-4" /> Upload First Document</Button>
                  </Link>
                </div>
              ) : (
                <div className="divide-y divide-gray-50 border border-gray-100 rounded-xl overflow-hidden">
                  {documents.map((doc) => (
                    <div key={doc.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50">
                      <div className="flex items-center gap-3">
                        <FileText className="w-4 h-4 text-gray-400" />
                        <div>
                          <p className="text-sm font-medium text-gray-800">{doc.original_filename}</p>
                          <p className="text-xs text-gray-500">
                            {formatBytes(doc.file_size_bytes)}
                            {doc.page_count ? ` · ${doc.page_count} pages` : ""}
                            {doc.document_type ? ` · ${doc.document_type}` : ""}
                            {doc.avg_confidence ? ` · ${Math.round(doc.avg_confidence * 100)}% OCR confidence` : ""}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <ProcessingChip status={doc.status} />
                        <button
                          className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-red-200 text-red-600 hover:bg-red-50 transition-colors"
                          title="Remove document from case"
                          onClick={() => {
                            if (confirm(`Remove "${doc.original_filename}" from this case? This cannot be undone.`)) {
                              deleteDocMutation.mutate(doc.id);
                            }
                          }}
                        >
                          <XCircle className="w-3 h-3" />
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Contradictions ── */}
          {activeTab === "contradictions" && (
            <div className="space-y-4">
              {contradictions.length === 0 ? (
                <div className="grid md:grid-cols-2 gap-6 py-8">
                  {/* Left — call-to-action */}
                  <div className="flex flex-col items-start justify-center">
                    <AlertTriangle className="w-10 h-10 text-gray-200 mb-3" />
                    <h3 className="text-base font-semibold text-gray-900 mb-1">
                      No contradictions detected yet
                    </h3>
                    <p className="text-sm text-gray-500 mb-4 max-w-sm">
                      Upload audio recordings and supporting documents, then run analysis.
                      Vera will compare every claim and surface conflicts with timestamped citations.
                    </p>
                    <Button
                      onClick={() => analysisMutation.mutate()}
                      loading={analysisMutation.isPending}
                    >
                      <Zap className="w-4 h-4" /> Run Analysis
                    </Button>
                  </div>

                  {/* Right — faded preview of what a populated card looks like */}
                  <div className="relative" aria-hidden="true">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">
                      This is what you'll see ↓
                    </p>
                    <div className="border border-gray-100 rounded-xl p-4 space-y-3 opacity-50 select-none pointer-events-none">
                      <div className="rounded-lg p-2.5 bg-red-50 border border-red-200">
                        <div className="flex items-center gap-1.5 mb-0.5">
                          <Brain className="w-3 h-3 text-red-600" />
                          <p className="text-[10px] font-semibold uppercase tracking-wide text-red-700">
                            AI Analysis
                          </p>
                        </div>
                        <p className="text-xs font-medium text-gray-800">
                          Defendant claims he was home all evening, but the badge log places him outside the building from 23:08 to 02:41.
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold">CRITICAL</span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 font-semibold">
                          ✦ AI Suggested
                        </span>
                        <span className="text-[10px] text-gray-500">94% confidence</span>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div className="bg-blue-50 rounded-lg p-2">
                          <p className="text-[10px] font-semibold text-blue-700 mb-0.5 flex items-center gap-1">
                            <Mic className="w-2.5 h-2.5" />
                            Transcript · 2:14
                          </p>
                          <p className="text-[11px] text-gray-700 italic line-clamp-2">"I was home all evening…"</p>
                        </div>
                        <div className="bg-amber-50 rounded-lg p-2">
                          <p className="text-[10px] font-semibold text-amber-700 mb-0.5 flex items-center gap-1">
                            <FileText className="w-2.5 h-2.5" />
                            Doc · p. 3
                          </p>
                          <p className="text-[11px] text-gray-700 italic line-clamp-2">"Badge-out at 23:08, return at 02:41…"</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                contradictions.map((c, idx) => (
                  <ContradictionCard key={c.id} index={idx}><div
                    className="border border-gray-100 dark:border-navy-700 bg-white dark:bg-navy-800 rounded-xl p-5 space-y-3 hover:border-gray-200 dark:hover:border-navy-600 hover:shadow-md transition-all"
                  >
                    {/* AI conclusion — prominent at top */}
                    {c.explanation && (
                      <div className={`rounded-lg p-3 border ${
                        c.severity === "CRITICAL" ? "bg-red-50 border-red-200 dark:bg-red-500/10 dark:border-red-500/30" :
                        c.severity === "HIGH"     ? "bg-orange-50 border-orange-200 dark:bg-orange-500/10 dark:border-orange-500/30" :
                        "bg-gray-50 border-gray-200 dark:bg-navy-900/40 dark:border-navy-700"
                      }`}>
                        <div className="flex items-center gap-2 mb-1">
                          <Brain className={`w-3.5 h-3.5 flex-shrink-0 ${
                            c.severity === "CRITICAL" ? "text-red-600 dark:text-red-400" :
                            c.severity === "HIGH"     ? "text-orange-600 dark:text-orange-400" :
                            "text-gray-500 dark:text-gray-400"
                          }`} />
                          <p className={`text-xs font-semibold uppercase tracking-wide ${
                            c.severity === "CRITICAL" ? "text-red-700 dark:text-red-300" :
                            c.severity === "HIGH"     ? "text-orange-700 dark:text-orange-300" :
                            "text-gray-600 dark:text-gray-300"
                          }`}>AI Analysis</p>
                        </div>
                        <p className="text-sm font-medium text-gray-800 dark:text-gray-100">{c.explanation}</p>
                      </div>
                    )}

                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <SeverityBadge severity={c.severity} />
                        {/* Gold/amber AI_SUGGESTED badge for visibility */}
                        {c.status === "AI_SUGGESTED" ? (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-gold-500/15 dark:text-gold-300 dark:border-gold-500/30">
                            ✦ AI Suggested
                          </span>
                        ) : (
                          <StatusBadge status={c.status} />
                        )}
                        <span
                          className="text-xs text-gray-500 dark:text-gray-400 cursor-help"
                          title="Confidence reflects semantic distance between the two statements and specificity of the detected contradiction."
                        >
                          {Math.round(c.confidence_score * 100)}% confidence
                        </span>
                      </div>
                      {c.contradiction_type && (
                        <span className="text-xs bg-gray-100 text-gray-600 dark:bg-navy-700 dark:text-gray-300 px-2 py-0.5 rounded capitalize">
                          {formatLabel(c.contradiction_type)}
                        </span>
                      )}
                    </div>

                    {/* Evidence side-by-side */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="bg-blue-50 dark:bg-blue-500/10 rounded-lg p-3">
                        <p className="text-xs font-semibold text-blue-700 dark:text-blue-400 mb-1 flex items-center gap-1">
                          <Mic className="w-3 h-3" />
                          Transcript
                          {c.transcript_speaker ? ` — ${c.transcript_speaker}` : ""}
                          {c.transcript_timestamp_start != null
                            ? ` @ ${formatTimestamp(c.transcript_timestamp_start)}`
                            : ""}
                        </p>
                        <p className="text-sm text-gray-800 dark:text-gray-200 italic">"{c.transcript_text}"</p>
                      </div>
                      <div className="bg-amber-50 dark:bg-amber-500/10 rounded-lg p-3">
                        <p className="text-xs font-semibold text-amber-700 dark:text-amber-400 mb-1 flex items-center gap-1">
                          <FileText className="w-3 h-3" />
                          Document{c.document_page ? ` — Page ${c.document_page}` : ""}
                        </p>
                        <p className="text-sm text-gray-800 dark:text-gray-200 italic">"{c.document_text}"</p>
                      </div>
                    </div>

                    {c.attorney_notes && (
                      <div className="bg-navy-50 dark:bg-navy-700/40 rounded-lg p-3">
                        <p className="text-xs font-medium text-navy-600 dark:text-gold-300 mb-1">Attorney Notes:</p>
                        <p className="text-sm text-gray-700 dark:text-gray-200">{c.attorney_notes}</p>
                      </div>
                    )}

                    {c.status === "AI_SUGGESTED" && (
                      <div className="pt-1">
                        <p className="text-xs text-gray-400 dark:text-gray-500 mb-2">
                          Your decision will be recorded with your name and timestamp.
                        </p>
                        {reviewingId === c.id ? (
                          <div className="space-y-2">
                            <textarea
                              value={reviewNotes}
                              onChange={(e) => setReviewNotes(e.target.value)}
                              placeholder="Attorney notes (optional) — auto-saved with timestamp"
                              rows={2}
                              className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-navy-500"
                            />
                            <div className="flex gap-2">
                              <Button
                                size="sm"
                                onClick={() => reviewMutation.mutate({ id: c.id, status: "CONFIRMED", notes: reviewNotes })}
                                loading={reviewMutation.isPending}
                                className="bg-green-600 hover:bg-green-700"
                                title="Mark this contradiction as verified for inclusion in your legal report."
                              >
                                <CheckCircle className="w-3 h-3" /> Confirm
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => reviewMutation.mutate({ id: c.id, status: "REJECTED", notes: reviewNotes })}
                                loading={reviewMutation.isPending}
                                className="text-red-600 border-red-200 hover:bg-red-50"
                                title="Remove this contradiction from your report. The AI suggestion will be logged."
                              >
                                <XCircle className="w-3 h-3" /> Reject
                              </Button>
                              <Button
                                size="sm"
                                variant="ghost"
                                onClick={() => { setReviewingId(null); setReviewNotes(""); }}
                              >
                                Cancel
                              </Button>
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setReviewingId(c.id)}
                          >
                            Review Contradiction
                          </Button>
                        )}
                      </div>
                    )}
                  </div></ContradictionCard>
                ))
              )}
            </div>
          )}

          {/* ── Ask AI (formerly Case Query) ── */}
          {activeTab === "query" && (
            <div className="text-center py-12">
              <div className="w-14 h-14 rounded-full bg-gold-500 mx-auto mb-4 flex items-center justify-center">
                <MessageSquare className="w-7 h-7 text-white" />
              </div>
              <p className="text-gray-700 font-semibold text-lg mb-1">Ask AI — Evidence Q&amp;A</p>
              <p className="text-gray-500 text-sm mb-4 max-w-md mx-auto">
                Ask anything in plain English. Vera, your AI legal assistant, will cite every answer
                to exact transcript timestamps and document pages.
              </p>
              <Link to={`/cases/${caseId}/query`}>
                <Button>
                  <MessageSquare className="w-4 h-4" />
                  Open AI Assistant
                </Button>
              </Link>
            </div>
          )}

          {/* ── Reports ── */}
          {activeTab === "reports" && (
            <div className="space-y-4">
              <div className="flex justify-between items-center">
                <h3 className="font-medium text-gray-900">Generated Reports</h3>
                <Button
                  size="sm"
                  onClick={() => reportMutation.mutate()}
                  loading={reportMutation.isPending}
                >
                  <Download className="w-4 h-4" />
                  Generate Report
                </Button>
              </div>

              {reportsLoading ? (
                <div className="animate-pulse space-y-3">
                  {[1,2].map(i => <div key={i} className="h-14 bg-gray-100 rounded-lg" />)}
                </div>
              ) : reports.length === 0 ? (
                <div className="text-center py-12 border-2 border-dashed border-gray-200 rounded-xl">
                  <BarChart3 className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                  <p className="text-gray-500 text-sm">No reports generated yet.</p>
                </div>
              ) : (
                <div className="divide-y divide-gray-50 border border-gray-100 rounded-xl overflow-hidden">
                  {reports.map((r) => (
                    <div key={r.id} className="flex items-center justify-between px-4 py-3 hover:bg-gray-50">
                      <div>
                        <p className="text-sm font-medium text-gray-800">{r.title}</p>
                        <p className="text-xs text-gray-500">
                          {r.format} · {format(new Date(r.created_at), "MMM d, yyyy")}
                          {r.page_count ? ` · ${r.page_count} pages` : ""}
                        </p>
                        {(r.status === "GENERATING" || r.status === "QUEUED") && (
                          <p className="text-xs text-amber-600 mt-1">
                            {r.status === "QUEUED" ? "In queue — processing shortly…" : "Generating — approx. 2–3 minutes"}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-2">
                        <ProcessingChip status={r.status} />
                        {r.status === "COMPLETE" && r.download_url && (
                          <a
                            href={r.download_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded bg-navy-600 text-white hover:bg-navy-700"
                          >
                            <Download className="w-3 h-3" /> Download
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ───── Helpers ────────────────────────────────────────────────────────────

interface ContradictionCardProps {
  index: number;
  children: React.ReactNode;
}

/** Wraps each contradiction card in a staggered fade/slide entry. */
function ContradictionCard({ index, children }: ContradictionCardProps) {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: "easeOut", delay: reduce ? 0 : 0.06 * index }}
    >
      {children}
    </motion.div>
  );
}
