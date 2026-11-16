import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { ScheduleStatusBadge } from "@/components/ScheduleBadge";
import { formatDateTime } from "@/utils/format";
import type { Page, ScheduleListItem } from "@/types";

export default function SchedulesPage() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, status]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["schedules", debounced, status, page],
    queryFn: async () => (await api.get<Page<ScheduleListItem>>("/schedules", { params: { search: debounced || undefined, status: status || undefined, page, page_size: 15 } })).data,
  });
  return (
    <>
      <PageHeader title="Test schedules" description="Online assessments scheduled for approved applicants. Schedule one from an assessment's page once a version is published." />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search schedules" placeholder="Search applicant or opening" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by status" className="w-full sm:w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {["invited", "accepted", "in_progress", "completed", "expired", "cancelled"].map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No schedules" description={debounced || status ? "Try changing the filters." : "Nothing is scheduled yet."} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Applicant</th><th className={th}>Window</th><th className={th}>Duration</th><th className={th}>Status</th></tr></thead>
              <tbody>
                {data.items.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/schedules/${s.id}`} className="font-medium text-slate-900 hover:underline">{s.candidate_name}</Link><span className="block text-xs text-slate-500">{s.opening_title}</span></td>
                    <td className={`${td} text-sm`}>{formatDateTime(s.window_start)}<span className="block text-xs text-slate-500">to {formatDateTime(s.window_end)}</span></td>
                    <td className={`${td} tabular-nums`}>{s.duration_minutes} min</td>
                    <td className={td}><div className="flex flex-wrap gap-1"><ScheduleStatusBadge status={s.status} />{s.pending_reschedule && <Badge tone="amber">Reschedule requested</Badge>}</div></td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
    </>
  );
}
