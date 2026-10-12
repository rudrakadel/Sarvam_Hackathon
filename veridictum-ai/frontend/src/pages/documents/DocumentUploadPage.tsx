/**
 * VeriDictum AI — Document Upload Page (UC-20)
 * Drag-and-drop upload for PDF/DOCX/TXT legal documents.
 * Triggers intelligent OCR and text extraction on success.
 */

import { useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useDropzone } from "react-dropzone";
import { useMutation } from "@tanstack/react-query";
import { FileText, Upload, CheckCircle, AlertCircle, X, ChevronRight } from "lucide-react";
import toast from "react-hot-toast";
import { documentsApi, casesApi } from "@/services/api";
import { Button } from "@/components/atoms/Button";
import { clsx } from "clsx";

const ACCEPTED_DOCS = {
  "application/pdf": [".pdf"],
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
  "application/msword": [".doc"],
  "text/plain": [".txt"],
};

const MAX_SIZE = 100 * 1024 * 1024; // 100 MB

export function DocumentUploadPage() {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();

  const { data: caseData } = useQuery({
    queryKey: ["case", caseId],
    queryFn: () => casesApi.get(caseId!),
    enabled: !!caseId,
  });
  const caseTitle = caseData?.data?.title ?? "Case";

  const mutation = useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return documentsApi.upload(caseId!, formData);
    },
    onSuccess: () => {
      toast.success("Document uploaded — text extraction started.");
      setTimeout(() => navigate(`/cases/${caseId}`), 1500);
    },
    onError: () => toast.error("Upload failed. Please try again."),
  });

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted[0]) mutation.mutate(accepted[0]);
    },
    [mutation]
  );

  const {
    getRootProps,
    getInputProps,
    isDragActive,
    acceptedFiles,
    fileRejections,
  } = useDropzone({
    onDrop,
    accept: ACCEPTED_DOCS,
    maxSize: MAX_SIZE,
    multiple: false,
  });

  const file = acceptedFiles[0];
  const rejection = fileRejections[0];

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

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
        <span className="text-gray-900 font-medium">Upload Document</span>
      </nav>

      <div>
        <h1 className="text-2xl font-bold text-gray-900">Upload Document</h1>
        <p className="text-gray-500 text-sm mt-1">
          PDF, DOCX, DOC, TXT — up to 100 MB. Text is automatically extracted from all
          pages and indexed for contradiction analysis.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6 space-y-5">
        {/* Drop zone */}
        <div
          {...getRootProps()}
          className={clsx(
            "border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors",
            isDragActive
              ? "border-navy-500 bg-navy-50"
              : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
          )}
        >
          <input {...getInputProps()} />

          {mutation.isPending ? (
            <div className="space-y-3">
              <div className="w-12 h-12 border-2 border-navy-600 border-t-transparent rounded-full animate-spin mx-auto" />
              <p className="text-sm text-gray-600 font-medium">Uploading & queuing for OCR...</p>
              <p className="text-xs text-gray-400">This may take a moment for large files.</p>
            </div>
          ) : mutation.isSuccess ? (
            <div className="space-y-2">
              <CheckCircle className="w-12 h-12 text-green-500 mx-auto" />
              <p className="text-sm font-medium text-green-700">Upload successful!</p>
              <p className="text-xs text-gray-500">OCR is running in the background. Redirecting...</p>
            </div>
          ) : (
            <>
              <FileText className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              {file ? (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900">{file.name}</p>
                  <p className="text-xs text-gray-500">{formatSize(file.size)}</p>
                  <p className="text-xs text-gray-400 mt-2">
                    Drop another file to replace, or click Upload below
                  </p>
                </div>
              ) : (
                <>
                  <p className="text-sm font-medium text-gray-700">
                    {isDragActive ? "Drop the document here" : "Drag & drop document here"}
                  </p>
                  <p className="text-xs text-gray-500 mt-1">or click to browse</p>
                  <p className="text-xs text-gray-400 mt-2">
                    PDF · DOCX · DOC · TXT — max 100 MB
                  </p>
                </>
              )}
            </>
          )}
        </div>

        {/* Rejection error */}
        {rejection && (
          <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-red-700">
                {rejection.errors[0]?.code === "file-too-large"
                  ? "File exceeds the 100 MB limit."
                  : "Unsupported file type."}
              </p>
              <p className="text-xs text-red-600 mt-0.5">
                Accepted formats: PDF, DOCX, DOC, TXT
              </p>
            </div>
          </div>
        )}

        {/* Upload API error */}
        {mutation.isError && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg">
            <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
            <p className="text-sm text-red-700">Upload failed. Please try again.</p>
          </div>
        )}

        {/* Info box */}
        {!mutation.isPending && !mutation.isSuccess && (
          <div className="rounded-lg bg-blue-50 border border-blue-100 p-4 space-y-1.5">
            <p className="text-xs font-semibold text-blue-800">What happens after upload?</p>
            <ul className="text-xs text-blue-700 space-y-1 list-disc list-inside">
              <li>Text is automatically extracted from all pages</li>
              <li>Quality confidence scores are calculated per page</li>
              <li>Your document is indexed for contradiction detection and case queries</li>
              <li>Processing takes 1–3 minutes</li>
            </ul>
          </div>
        )}

        {/* Actions */}
        {!mutation.isSuccess && (
          <div className="flex gap-3 pt-1">
            <Button
              onClick={() => file && mutation.mutate(file)}
              disabled={!file || mutation.isPending}
              loading={mutation.isPending}
            >
              <Upload className="w-4 h-4" />
              {mutation.isPending ? "Uploading…" : "Upload Document"}
            </Button>
            <Button
              variant="outline"
              onClick={() => navigate(`/cases/${caseId}`)}
              disabled={mutation.isPending}
            >
              <X className="w-4 h-4" />
              Cancel
            </Button>
          </div>
        )}
      </div>

      <p className="text-xs text-gray-400 text-center">
        Uploaded documents are stored with end-to-end encryption and are accessible
        only to authorized case members.
      </p>
    </div>
  );
}
