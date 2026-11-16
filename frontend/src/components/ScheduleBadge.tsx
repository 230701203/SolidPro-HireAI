import { Badge } from "@/components/ui";
import type { ScheduleStatus } from "@/types";

const MAP: Record<ScheduleStatus, { tone: "green" | "amber" | "red" | "slate" | "blue" | "purple"; label: string }> = {
  invited: { tone: "amber", label: "Invited" },
  accepted: { tone: "blue", label: "Accepted" },
  in_progress: { tone: "purple", label: "In progress" },
  completed: { tone: "green", label: "Completed" },
  expired: { tone: "slate", label: "Expired" },
  cancelled: { tone: "red", label: "Cancelled" },
};

export function ScheduleStatusBadge({ status }: { status: ScheduleStatus }) {
  const m = MAP[status];
  return <Badge tone={m.tone}>{m.label}</Badge>;
}

/** "2026-12-01T10:00" (local) -> ISO string with timezone offset, as the API requires. */
export function localToIso(v: string): string {
  return new Date(v).toISOString();
}
