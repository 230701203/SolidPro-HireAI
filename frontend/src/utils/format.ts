export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} d ago`;
  return formatDate(iso);
}

export function humanize(code: string): string {
  return code.replace(/[._]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const STATUS_LABELS: Record<string, string> = {
  pending_email_verification: "Awaiting email verification",
  pending_approval: "Pending approval",
  active: "Active",
  rejected: "Rejected",
  suspended: "Suspended",
  deactivated: "Deactivated",
};
