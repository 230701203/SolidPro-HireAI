import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Card, EmptyState, ErrorState, PageHeader, Pagination, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { formatDate } from "@/utils/format";
import type { ApplicantListItem, Page } from "@/types";

export default function ApplicantsPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced]);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["applicants", debounced, page],
    queryFn: async () => (await api.get<Page<ApplicantListItem>>("/applicants", { params: { search: debounced || undefined, page, page_size: 15 } })).data,
  });
  return (
    <>
      <PageHeader title="Applicants" description="People who applied to openings you can access." />
      <Card>
        <div className="border-b border-slate-200 p-4">
          <div className="relative max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search applicants" placeholder="Search name, email or mobile" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No applicants found" description={debounced ? "Try a different search." : "Applicants appear here once they apply to your openings."} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Applicant</th><th className={th}>Mobile</th><th className={th}>City</th><th className={th}>Qualification</th><th className={th}>Applications</th><th className={th}>Joined</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.candidate_id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/applicants/${a.candidate_id}`} className="font-medium text-slate-900 hover:underline">{a.full_name}</Link><span className="block text-xs text-slate-500">{a.email}</span></td>
                    <td className={td}>{a.mobile ?? "—"}</td><td className={td}>{a.city ?? "—"}</td><td className={td}>{a.highest_qualification ?? "—"}</td>
                    <td className={`${td} tabular-nums`}>{a.applications_count}</td><td className={td}>{formatDate(a.created_at)}</td>
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
