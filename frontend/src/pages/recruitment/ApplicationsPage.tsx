import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import { formatDate } from "@/utils/format";
import { APPLICATION_STATUS_LABELS } from "@/utils/labels";
import type { ApplicationListItem, ApplicationStatus, Page } from "@/types";

export default function ApplicationsPage() {
  const [params] = useSearchParams();
  const openingId = params.get("opening_id") || undefined;
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, status, openingId]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["applications", debounced, status, openingId, page],
    queryFn: async () => (await api.get<Page<ApplicationListItem>>("/applications", { params: { search: debounced || undefined, status: status || undefined, opening_id: openingId, page, page_size: 15 } })).data,
  });
  return (
    <>
      <PageHeader title="Applications" description={openingId ? "Filtered to one opening." : "Review applications for openings you can access."} actions={openingId && <Link to="/applications" className="text-sm text-brand-700 hover:underline">Clear opening filter</Link>} />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search applications" placeholder="Search applicant or opening" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by status" className="w-full sm:w-48" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {(Object.keys(APPLICATION_STATUS_LABELS) as ApplicationStatus[]).map((s) => <option key={s} value={s}>{APPLICATION_STATUS_LABELS[s]}</option>)}
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No applications found" description="Try changing the filters." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Applicant</th><th className={th}>Opening</th><th className={th}>Status</th><th className={th}>Submitted</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/applications/${a.id}`} className="font-medium text-slate-900 hover:underline">{a.candidate_name}</Link><span className="block text-xs text-slate-500">{a.candidate_email}</span></td>
                    <td className={td}>{a.opening_title}<span className="block text-xs text-slate-500">{a.category_name}</span></td>
                    <td className={td}><ApplicationStatusBadge status={a.status} /></td>
                    <td className={td}>{formatDate(a.submitted_at)}</td>
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
