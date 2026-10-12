/**
 * VeriDictum AI — Audio Upload Page (UC-19)
 * Drag-and-drop audio upload with progress indicator.
 */

import { useState, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { useMutation } from "@tanstack/react-query";
import { Mic, CheckCircle, AlertCircle, Upload, X, ChevronRight } from "lucide-react";
import toast from "react-hot-toast";
import { audioApi, casesApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { Input } from "@/components/atoms/Input";
import { clsx } from "clsx";

const ACCEPTED_AUDIO = {
  "audio/mpeg": [".mp3"],
  "audio/mp4": [".mp4", ".m4a"],
  "audio/wav": [".wav"],
  "audio/ogg": [".ogg"],
};

const MAX_SIZE = 5 * 1024 * 1024 * 1024; // 5 GB

export function AudioUploadPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const [languageHint, setLanguageHint] = useState("");
  const [speakerCount, setSpeakerCount] = useState("");

  const { data: caseData } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
  });
  const caseTitle = caseData?.data?.title ?? "Case";
  const mutation = useMutation({
    mutationFn: ({ file }: { file: File }) => {
      const formData = new FormData();
      formData.append("file", file);
      if (languageHint) formData.append("language_hint", languageHint);
      if (speakerCount) formData.append("speaker_count_hint", speakerCount);
      return audioApi.upload(caseId!, formData);
    },
    onSuccess: () => {
      toast.success("Audio uploaded — transcription started.");
      setTimeout(() => navigate(`/cases/${caseId}`), 1500);
    },
    onError: () => toast.error("Upload failed. Please try again."),
  });

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) mutation.mutate({ file: accepted[0] });
    },
    [mutation]
  );

  const { getRootProps, getInputProps, isDragActive, acceptedFiles, fileRejections } = useDropzone({
    onDrop,
    accept: ACCEPTED_AUDIO,
    maxSize: MAX_SIZE,
    multiple: false,
  });

  const file = acceptedFiles[0];
  const rejection = fileRejections[0];

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-1.5 text-sm text-gray-500" aria-label="Breadcrumb">
        <Link to="/cases" className="hover:text-gray-700 transition-colors">Cases</Link>
        <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        <Link to={`/cases/${caseId}`} className="hover:text-gray-700 transition-colors truncate max-w-[180px]">
          {caseTitle}
        </Link>
        <ChevronRight className="w-3.5 h-3.5 flex-shrink-0" />
        <span className="text-gray-900 font-medium">Upload Audio</span>
      </nav>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Audio Recording</h1>
        <p className="text-gray-500 text-sm mt-1">
          MP3, MP4, WAV, M4A, OGG — up to 5 GB. Whisper Large v3 transcription with speaker diarization.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 space-y-5">
        {/* Drop zone */}
        <div
          {...getRootProps()}
          className={clsx(
            "border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors",
            isDragActive ? "border-navy-500 bg-navy-50" : "border-gray-200 hover:border-gray-300"
          )}
        >
          <input {...getInputProps()} />
          {mutation.isPending ? (
            <div className="space-y-3">
              <div className="w-12 h-12 border-2 border-navy-600 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-gray-600">Uploading & queuing for transcription...</p>
            </div>
          ) : mutation.isSuccess ? (
            <div className="space-y-2">
              <CheckCircle className="w-12 h-12 text-green-500 mx-auto" />
              <p className="text-sm font-medium text-green-700">Upload successful! Redirecting...</p>
            </div>
          ) : (
            <>
              <Mic className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              {file ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900">{file.name}</p>
                  <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
                </div>
              ) : (
                <>
                  <p className="text-sm font-medium text-gray-700">
                    {isDragActive ? "Drop the audio file here" : "Drag & drop audio file here"}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">or click to browse</p>
                  <p className="text-xs text-gray-400 mt-2">MP3 · MP4 · WAV · M4A · OGG — max 5 GB</p>
                </>
              )}
            </>
          )}
        </div>

        {rejection && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">
              {rejection.errors[0]?.code === "file-too-large"
                ? "File exceeds 5 GB limit."
                : "Unsupported file type."}
            </p>
          </div>
        )}

        {/* Optional settings */}
        <div className="grid grid-cols-2 gap-4 pt-2">
          <Input
            label="Language Hint (optional)"
            placeholder="en, fr, es..."
            value={languageHint}
            onChange={(e) => setLanguageHint(e.target.value)}
            hint="ISO 639-1 language code improves accuracy"
          />
          <Input
            label="Speaker Count Hint (optional)"
            type="number"
            min={2}
            max={12}
            placeholder="2-12"
            value={speakerCount}
            onChange={(e) => setSpeakerCount(e.target.value)}
            hint="Number of speakers in the recording"
          />
        </div>

        {!mutation.isSuccess && (
          <div className="flex gap-3 pt-2">
            {file && !mutation.isPending ? (
              <Button onClick={() => mutation.mutate({ file })}>
                <Upload className="w-4 h-4" />
                Upload & Transcribe
              </Button>
            ) : !mutation.isPending ? (
              <Button disabled>
                <Upload className="w-4 h-4" />
                Upload & Transcribe
              </Button>
            ) : null}
            <Button
              variant="outline"
              onClick={() => navigate(`/cases/${caseId}`)}
            >
              <X className="w-4 h-4" />
              Cancel
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
