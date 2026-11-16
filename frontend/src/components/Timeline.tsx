import { EyeOff } from "lucide-react";
import { ApplicationStatusBadge } from "@/components/badges";
import { formatDateTime } from "@/utils/format";
import type { HistoryItem } from "@/types";

export default function Timeline({ items, staff }: { items: HistoryItem[]; staff?: boolean }) {
  if (items.length === 0) return <p className="text-sm text-slate-500">No activity yet.</p>;
  return (
    <ol className="relative space-y-5 border-l border-slate-200 pl-5">
      {items.map((h) => {
        const commentOnly = h.from_status === h.to_status;
        return (
          <li key={h.id} className="relative">
            <span className={`absolute -left-[26px] top-1.5 size-3 rounded-full border-2 border-white ${commentOnly ? "bg-slate-400" : "bg-brand-600"}`} />
            <div className="flex flex-wrap items-center gap-2">
              {commentOnly ? <span className="text-sm font-medium text-slate-700">Note</span> : <ApplicationStatusBadge status={h.to_status} />}
              {staff && !h.visible_to_applicant && (
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"><EyeOff className="size-3" /> Internal, hidden from applicant</span>
              )}
            </div>
            {h.comment && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-700">{h.comment}</p>}
            <p className="mt-0.5 text-xs text-slate-500">{h.actor_name ?? "System"} · {formatDateTime(h.created_at)}</p>
          </li>
        );
      })}
    </ol>
  );
}
