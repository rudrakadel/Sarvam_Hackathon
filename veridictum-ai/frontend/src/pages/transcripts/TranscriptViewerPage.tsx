/**
 * VeriDictum AI — Transcript Viewer Page (UC-21, UC-22)
 * Speaker-labelled transcript with inline editing.
 */

import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Edit2, Save, X, User, Sparkles } from "lucide-react";
import { audioApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import type { Transcript, TranscriptSegment } from "@/types";

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const SPEAKER_COLORS = [
  "bg-blue-100 text-blue-800 border-blue-200",
  "bg-purple-100 text-purple-800 border-purple-200",
  "bg-green-100 text-green-800 border-green-200",
  "bg-orange-100 text-orange-800 border-orange-200",
  "bg-pink-100 text-pink-800 border-pink-200",
];

export function TranscriptViewerPage() {
  const { caseId, audioId, transcriptId } = useParams<{
    caseId: string;
    audioId: string;
    transcriptId: string;
  }>();
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editText, setEditText] = useState("");

  const { data: transcriptsData } = useQuery({
    queryKey: ["transcripts", audioId],
    queryFn: () => audioApi.listTranscripts(caseId!, audioId!),
    enabled: !!(caseId && audioId),
  });

  const { data: segmentsData, isLoading } = useQuery({
    queryKey: ["segments", transcriptId],
    queryFn: () => audioApi.getSegments(caseId!, audioId!, transcriptId!),
    enabled: !!(caseId && audioId && transcriptId),
  });

  const editMutation = useMutation({
    mutationFn: ({ segmentId, text }: { segmentId: string; text: string }) =>
      audioApi.editSegment(caseId!, audioId!, transcriptId!, segmentId, text),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["segments", transcriptId] });
      setEditingId(null);
    },
  });

  const summarizeMutation = useMutation({
    mutationFn: () => audioApi.summarizeTranscript(caseId!, audioId!, transcriptId!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["transcripts", audioId] });
    },
  });

  const segments: TranscriptSegment[] = segmentsData?.data || [];
  const currentTranscript: Transcript | undefined = (transcriptsData?.data || []).find(
    (t: Transcript) => t.id === transcriptId
  ) || transcriptsData?.data?.[0];

  // Assign consistent colours to speakers
  const speakerSet = [...new Set(segments.map((s) => s.speaker_label))];
  const speakerColorMap: Record<string, string> = {};
  speakerSet.forEach((sp, i) => {
    speakerColorMap[sp] = SPEAKER_COLORS[i % SPEAKER_COLORS.length];
  });

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Transcript & Testimony Intelligence</h1>
          <p className="text-sm text-gray-500">Real-time Sarvam STT transcription with automated claim summarization.</p>
        </div>
      </div>

      {/* Sarvam AI Testimony Summary Card */}
      <div className="bg-gradient-to-br from-indigo-50/70 via-white to-blue-50/50 rounded-xl border border-indigo-100 p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="p-1.5 bg-indigo-600 text-white rounded-lg flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </span>
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                AI Testimony Summary (Powered by Sarvam)
              </h2>
              <p className="text-xs text-gray-500">
                Structured Witness Claims, Admissions & Chronology
              </p>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={() => summarizeMutation.mutate()}
            loading={summarizeMutation.isPending}
          >
            Refresh AI Summary
          </Button>
        </div>

        {currentTranscript?.summary ? (
          <div className="prose prose-sm max-w-none text-gray-800 text-sm whitespace-pre-wrap leading-relaxed bg-white/90 p-4 rounded-lg border border-indigo-100">
            {currentTranscript.summary}
          </div>
        ) : (
          <div className="text-sm text-gray-500 italic py-2">
            No summary generated yet. Click "Refresh AI Summary" to extract legal summary via Sarvam.
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-2">
        <h2 className="text-base font-semibold text-gray-900">Transcript Segments</h2>
        <p className="text-xs text-gray-500">Click any segment text to edit inline.</p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-2 border-navy-600 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : segments.length === 0 ? (
        <div className="text-center py-12 text-gray-500 text-sm">No segments found.</div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm divide-y divide-gray-50">
          {segments.map((seg) => (
            <div
              key={seg.id}
              className="flex gap-4 px-6 py-4 hover:bg-gray-50 transition-colors group"
            >
              {/* Timestamp */}
              <div className="flex-shrink-0 w-14 text-xs font-mono text-gray-400 pt-1">
                {formatTime(seg.start_time)}
              </div>

              {/* Speaker */}
              <div className="flex-shrink-0 w-32">
                <span
                  className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium border ${
                    speakerColorMap[seg.speaker_label]
                  }`}
                >
                  <User className="w-3 h-3" />
                  {seg.speaker_name || seg.speaker_label}
                </span>
                {seg.is_edited && (
                  <span className="block mt-1 text-xs text-amber-600">edited</span>
                )}
              </div>

              {/* Text */}
              <div className="flex-1">
                {editingId === seg.id ? (
                  <div className="space-y-2">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      rows={3}
                      className="w-full text-sm border border-navy-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-navy-500"
                      autoFocus
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => editMutation.mutate({ segmentId: seg.id, text: editText })}
                        loading={editMutation.isPending}
                      >
                        <Save className="w-3 h-3" />
                        Save
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setEditingId(null)}
                      >
                        <X className="w-3 h-3" />
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <p
                    className="text-sm text-gray-800 leading-relaxed cursor-text hover:bg-yellow-50 rounded px-1 -mx-1 transition-colors"
                    onClick={() => {
                      setEditingId(seg.id);
                      setEditText(seg.text);
                    }}
                    title="Click to edit"
                  >
                    {seg.text}
                  </p>
                )}
              </div>

              {/* Edit button (hover) */}
              {editingId !== seg.id && (
                <button
                  onClick={() => {
                    setEditingId(seg.id);
                    setEditText(seg.text);
                  }}
                  className="flex-shrink-0 opacity-0 group-hover:opacity-100 p-1.5 rounded text-gray-400 hover:text-navy-600 transition-all"
                  title="Edit segment"
                >
                  <Edit2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
