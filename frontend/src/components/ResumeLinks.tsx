import { Download, ExternalLink, FileText } from "lucide-react";
import { formatDate } from "@/utils/format";
import { formatBytes } from "@/utils/labels";
import type { Resume } from "@/types";

/** Files are served by the authorised API endpoint; the session cookie is sent automatically. */
export default function ResumeLinks({ resume }: { resume: Resume }) {
  const isPdf = resume.content_type === "application/pdf";
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 px-3 py-2.5">
      <FileText className="size-5 shrink-0 text-brand-600" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-slate-900">{resume.original_filename}</p>
        <p className="text-xs text-slate-500">Version {resume.version} · {formatBytes(resume.size_bytes)} · {formatDate(resume.created_at)}{resume.is_current ? " · current" : ""}</p>
      </div>
      {isPdf && (
        <a href={`/api/resumes/${resume.id}/file`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
          <ExternalLink className="size-4" /> Preview
        </a>
      )}
      <a href={`/api/resumes/${resume.id}/file?download=true`} className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline">
        <Download className="size-4" /> Download
      </a>
    </div>
  );
}
