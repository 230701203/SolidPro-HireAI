import { Badge } from "@/components/ui";
import { APPLICATION_STATUS_LABELS, OPENING_STATUS_LABELS } from "@/utils/labels";
import type { ApplicationStatus, OpeningStatus } from "@/types";

const APP_TONE: Record<ApplicationStatus, "slate" | "blue" | "amber" | "green" | "red" | "purple"> = {
  submitted: "slate",
  under_review: "blue",
  info_requested: "amber",
  approved: "green",
  shortlisted: "purple",
  selected: "green",
  rejected: "red",
  withdrawn: "slate",
};

export function ApplicationStatusBadge({ status }: { status: ApplicationStatus }) {
  return <Badge tone={APP_TONE[status]}>{APPLICATION_STATUS_LABELS[status]}</Badge>;
}

export function OpeningStatusBadge({ status, open }: { status: OpeningStatus; open?: boolean }) {
  if (status === "published" && open === false) return <Badge tone="amber">Deadline passed</Badge>;
  return <Badge tone={status === "published" ? "green" : status === "closed" ? "red" : "slate"}>{OPENING_STATUS_LABELS[status]}</Badge>;
}
