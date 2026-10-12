/**
 * VeriDictum AI — Natural Language Query Interface (FR-28/29)
 * AI assistant "Vera" with streaming indicators, markdown responses, and formatted citations.
 */

import { useState, useRef, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Send, FileText, Mic, ChevronRight } from "lucide-react";
import toast from "react-hot-toast";
import { motion } from "framer-motion";
import { queryApi, casesApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { VeraAvatar } from "@/components/atoms/VeraAvatar";
import { formatTimestamp, formatResponseTime } from "@/utils/format";
import { useReducedMotion } from "@/hooks/useReducedMotion";
import type { NLQuery } from "@/types";

/** Strip raw [SOURCE: ...] tags from answer text */
function cleanAnswer(text: string): string {
  return text.replace(/\[SOURCE:[^\]]*\]/g, "").replace(/\s{2,}/g, " ").trim();
}

/** Render answer text with basic markdown-like structure.
 *  Bold **text**, bullet points starting with "- " or "• ", and paragraph breaks. */
function FormattedAnswer({ text }: { text: string }) {
  const cleaned = cleanAnswer(text);
  const lines = cleaned.split("\n").filter(Boolean);

  return (
    <div className="text-sm text-gray-800 dark:text-gray-200 leading-relaxed space-y-2">
      {lines.map((line, i) => {
        // Bullet points
        if (line.trim().startsWith("- ") || line.trim().startsWith("• ")) {
          return (
            <div key={i} className="flex gap-2">
              <span className="text-navy-500 dark:text-gold-400 mt-1 flex-shrink-0">•</span>
              <span dangerouslySetInnerHTML={{ __html: boldify(line.replace(/^[-•]\s*/, "")) }} />
            </div>
          );
        }
        // Numbered lists
        if (/^\d+\.\s/.test(line.trim())) {
          return (
            <div key={i} className="flex gap-2">
              <span className="text-navy-500 dark:text-gold-400 font-medium flex-shrink-0">{line.match(/^\d+/)?.[0]}.</span>
              <span dangerouslySetInnerHTML={{ __html: boldify(line.replace(/^\d+\.\s*/, "")) }} />
            </div>
          );
        }
        // Headings (lines ending with ":")
        if (line.trim().endsWith(":") && line.trim().length < 60) {
          return <p key={i} className="font-semibold text-gray-900 dark:text-gray-100 mt-3">{line.trim()}</p>;
        }
        return <p key={i} dangerouslySetInnerHTML={{ __html: boldify(line) }} />;
      })}
    </div>
  );
}

function boldify(text: string): string {
  // Convert **bold** and *italic* to HTML
  return text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
}

export function NLQueryPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<NLQuery[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  const { data: caseData } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
  });
  const caseTitle = caseData?.data?.title ?? "Case";

  const { data: historyData } = useQuery({
    queryKey: ["query-history", caseId],
    queryFn: () => queryApi.history(caseId!, { page: 1, page_size: 50 }),
    enabled: !!caseId,
  });

  useEffect(() => {
    if (historyData?.data) {
      const items: NLQuery[] = historyData.data.items ?? historyData.data;
      setHistory([...items].reverse());
    }
  }, [historyData]);

  const mutation = useMutation({
    mutationFn: (query: string) => queryApi.ask(caseId!, query),
    onSuccess: (res) => {
      setHistory((prev) => [...prev, res.data as NLQuery]);
      setInput("");
    },
    onError: () => toast.error("Failed to get response. Please try again."),
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, mutation.isPending]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && !mutation.isPending) {
      mutation.mutate(input.trim());
    }
  };

  const EXAMPLE_QUERIES = [
    "What contradictions were found in this case?",
    "When did the defendant claim to be at home?",
    "Summarize the key evidence timeline",
    "What did witnesses state vs. what the defendant claimed?",
  ];

  return (
    <div className="max-w-4xl mx-auto flex flex-col h-[calc(100vh-8rem)]">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-gray-500 dark:text-gray-400 mb-3" aria-label="Breadcrumb">
        <Link to="/cases" className="hover:text-gray-700 dark:hover:text-gray-200 transition-colors">Cases</Link>
        <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        <Link to={`/cases/${caseId}`} className="hover:text-gray-700 dark:hover:text-gray-200 transition-colors truncate max-w-[180px]">
          {caseTitle}
        </Link>
        <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        <span className="text-gray-900 dark:text-gray-100 font-medium">Ask AI</span>
      </nav>

      {/* Header */}
      <div className="mb-4">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 flex items-center gap-3">
          <VeraAvatar size="md" thinking={mutation.isPending} />
          Ask AI — Evidence Q&amp;A
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
          Vera, your AI legal assistant, cites every answer to exact transcript timestamps and document pages.
        </p>
      </div>

      {/* Chat area */}
      <div
        ref={chatRef}
        className="flex-1 overflow-y-auto bg-white dark:bg-navy-800 rounded-xl border border-gray-100 dark:border-navy-700 shadow-sm mb-4 p-6 space-y-6"
      >
        {history.length === 0 && !mutation.isPending ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <VeraAvatar size="lg" className="mb-4" />
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100 mb-1">Hi, I'm Vera</h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-2 max-w-md">
              I've analyzed the evidence in this case. Ask me anything and I'll cite every answer to exact sources.
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mb-6">Powered by GPT-4.1 with retrieval-augmented generation</p>
            <div className="grid grid-cols-2 gap-3 w-full max-w-lg">
              {EXAMPLE_QUERIES.map((q) => (
                <button
                  key={q}
                  onClick={() => setInput(q)}
                  className="text-left text-sm px-4 py-3 rounded-xl border border-gray-200 dark:border-navy-700 text-gray-600 dark:text-gray-300 hover:border-navy-300 dark:hover:border-gold-400 hover:text-navy-700 dark:hover:text-gold-300 hover:bg-navy-50 dark:hover:bg-navy-700/40 transition-colors"
                >
                  "{q}"
                </button>
              ))}
            </div>
          </div>
        ) : (
          history.map((item, idx) => (
            <MessagePair key={item.id} item={item} index={idx} />
          ))
        )}

        {/* AI thinking indicator */}
        {mutation.isPending && (
          <div className="flex gap-3">
            <VeraAvatar size="sm" thinking />
            <div className="bg-gradient-to-br from-gold-50 to-white dark:from-gold-500/15 dark:to-navy-800 border border-gold-200/40 dark:border-gold-500/30 rounded-2xl rounded-tl-sm px-4 py-3 shadow-glow">
              <div className="flex items-center gap-2 text-navy-700 dark:text-gray-100">
                <ThinkingDots />
                <span className="text-sm">Vera is analyzing the evidence…</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask Vera anything about this case…"
          className="flex-1 rounded-xl border border-gray-200 dark:border-navy-700 bg-white dark:bg-navy-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 dark:placeholder:text-gray-500 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-navy-500 dark:focus:ring-gold-400 shadow-sm"
          disabled={mutation.isPending}
        />
        <Button
          type="submit"
          loading={mutation.isPending}
          disabled={!input.trim()}
        >
          <Send className="w-4 h-4" />
          Ask
        </Button>
      </form>

      <p className="text-xs text-gray-400 dark:text-gray-500 text-center mt-2">
        Answers are AI-generated and must be verified by an attorney before legal use.
      </p>
    </div>
  );
}

// ───── helpers below — kept in this file so the page stays self-contained ─

interface MessagePairProps {
  item: NLQuery;
  index: number;
}

function MessagePair({ item, index }: MessagePairProps) {
  const reduce = useReducedMotion();
  const initial = reduce ? false : { opacity: 0, y: 6 };
  const animate = { opacity: 1, y: 0 };
  return (
    <motion.div
      initial={initial}
      animate={animate}
      transition={{ duration: 0.32, ease: "easeOut", delay: Math.min(index * 0.04, 0.2) }}
      className="space-y-4"
    >
      {/* Question bubble */}
      <div className="flex justify-end">
        <div className="max-w-xl bg-navy-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm shadow-sm">
          {item.query_text}
        </div>
      </div>

      {/* Vera answer bubble */}
      <div className="flex gap-3">
        <VeraAvatar size="sm" />
        <div className="flex-1 space-y-3">
          <div className="bg-gradient-to-br from-gold-50/60 to-white dark:from-gold-500/10 dark:to-navy-800 border border-gold-200/40 dark:border-gold-500/30 rounded-2xl rounded-tl-sm px-4 py-3 shadow-sm">
            <FormattedAnswer text={item.answer_text} />
          </div>

          {/* Citation badges */}
          {item.citations && item.citations.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Sources · {item.citations.length}
              </p>
              <div className="flex flex-wrap gap-2">
                {item.citations.slice(0, 8).map((c, i) => {
                  const isTranscript = c.source_type === "transcript";
                  // Build the label so we NEVER render dangling "Doc p." or bare "@".
                  let label: string;
                  if (isTranscript) {
                    const speaker = c.speaker?.trim() || "Audio";
                    label = c.timestamp != null
                      ? `${speaker} · ${formatTimestamp(c.timestamp)}`
                      : speaker;
                  } else {
                    label = c.page != null ? `Doc · p. ${c.page}` : "Document";
                  }
                  return (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, scale: 0.9 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ duration: 0.22, delay: 0.04 * i }}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-medium ${
                        isTranscript
                          ? "bg-blue-50 border-blue-200 text-blue-700 dark:bg-blue-500/15 dark:border-blue-500/30 dark:text-blue-400"
                          : "bg-amber-50 border-amber-200 text-amber-700 dark:bg-amber-500/15 dark:border-amber-500/30 dark:text-amber-400"
                      }`}
                      title={
                        isTranscript
                          ? `Transcript citation — ${label}`
                          : `Document citation — ${label}`
                      }
                    >
                      {isTranscript ? (
                        <Mic className="w-3 h-3 flex-shrink-0" />
                      ) : (
                        <FileText className="w-3 h-3 flex-shrink-0" />
                      )}
                      <span className="truncate max-w-[200px]">{label}</span>
                    </motion.div>
                  );
                })}
              </div>
            </div>
          )}

          {item.response_time_ms != null && (
            <p className="text-xs text-gray-400 dark:text-gray-500">{formatResponseTime(item.response_time_ms)}</p>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** Three dots that rise + fall in a staggered ripple, Framer-Motion driven. */
function ThinkingDots() {
  const reduce = useReducedMotion();
  if (reduce) {
    // Static three dots — no animation. Still communicates "in progress".
    return (
      <div className="flex gap-1" aria-label="Vera is thinking">
        {[0, 1, 2].map((i) => (
          <span key={i} className="w-2 h-2 rounded-full bg-gold-500" />
        ))}
      </div>
    );
  }
  return (
    <div className="flex gap-1" aria-label="Vera is thinking">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-2 h-2 rounded-full bg-gold-500"
          animate={{ y: [0, -4, 0], opacity: [0.5, 1, 0.5] }}
          transition={{
            duration: 0.9,
            repeat: Infinity,
            ease: "easeInOut",
            delay: i * 0.15,
          }}
        />
      ))}
    </div>
  );
}
