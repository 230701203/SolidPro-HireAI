import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Card, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { ScheduleStatusBadge } from "@/components/ScheduleBadge";
import { formatDateTime } from "@/utils/format";
import type { Invitation } from "@/types";

export default function MyTestsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["my-tests"], queryFn: async () => (await api.get<Invitation[]>("/test-invitations")).data });
  return (
    <>
      <PageHeader title="My tests" description="Online assessments you have been invited to." />
      {isLoading ? <Spinner /> : error || !data ? <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card> : data.length === 0 ? (
        <Card><EmptyState title="No tests yet" description="When the recruitment team schedules an assessment for you, it appears here and in your email." /></Card>
      ) : (
        <ul className="space-y-3">
          {data.map((t) => (
            <li key={t.id}>
              <Link to={`/my-tests/${t.id}`} className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-brand-300">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="font-medium text-slate-900">{t.opening_title}</span>
                  <ScheduleStatusBadge status={t.status} />
                </div>
                <p className="mt-1 text-sm text-slate-600">{formatDateTime(t.window_start)} to {formatDateTime(t.window_end)} · {t.duration_minutes} minutes</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
