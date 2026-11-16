import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { Badge, Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import { formatDateTime } from "@/utils/format";
import type { EvalListItem, Page } from "@/types";

export default function ResultsPage() {
  const [params0] = useSearchParams();
  const [search, setSearch] = useState(params0.get("search") ?? "");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState(1);
  const { hasPermission } = useAuth();
  const nav = useNavigate();
  const [picked, setPicked] = useState<number[]>([]);
  const canCompare = hasPermission("view_analytics") && hasPermission("review_applications");
  const toggle = (id: number) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length < 5 ? [...p, id] : p));
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, filter]);
  const params: Record<string, string | number | boolean | undefined> = { search: debounced || undefined, page, page_size: 15 };
  if (filter === "needs_review") params.needs_review = true;
  if (filter === "draft" || filter === "final") params.status = filter;
  if (filter === "unreleased") { params.status = "final"; params.released = false; }
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["evaluations", debounced, filter, page], queryFn: async () => (await api.get<Page<EvalListItem>>("/evaluations", { params })).data });
  return (
    <>
      <PageHeader title="Results" description="Evaluated online assessments. Scores are advisory: a person reviews them, and nothing is decided automatically." />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search results" placeholder="Search applicant or opening" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter results" className="w-full sm:w-56" value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All results</option><option value="needs_review">Needs scoring</option><option value="draft">In review</option><option value="final">Approved</option><option value="unreleased">Approved, not released</option>
          </Select>
          {canCompare && <Button variant="secondary" disabled={picked.length < 2} onClick={() => nav(`/analytics/compare?ids=${picked.join(",")}`)}>Compare selected ({picked.length}/5)</Button>}
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No results" description={debounced || filter ? "Try changing the filters." : "Results appear here once applicants submit their tests."} />
        ) : (
          <>
            <TableWrap>
              <thead><tr>{canCompare && <th className={th}><span className="sr-only">Select</span></th>}<th className={th}>Applicant</th><th className={th}>Test date</th><th className={th}>Score</th><th className={th}>Review</th><th className={th}>Application</th></tr></thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/60">
                    {canCompare && <td className={td}><input type="checkbox" aria-label={`Select ${r.candidate_name} to compare`} checked={picked.includes(r.application_id)} onChange={() => toggle(r.application_id)} /></td>}
                    <td className={td}><Link to={`/results/${r.id}`} className="font-medium text-slate-900 hover:underline">{r.candidate_name}</Link><span className="block text-xs text-slate-500">{r.opening_title}</span></td>
                    <td className={`${td} text-sm`}>{formatDateTime(r.test_date)}</td>
                    <td className={`${td} tabular-nums`}>{r.total_obtained}/{r.total_marks}{r.percentage != null && <span className="ml-1 text-xs text-slate-500">({r.percentage}%)</span>}{r.unresolved > 0 && <span className="block text-xs text-amber-700">incomplete</span>}</td>
                    <td className={td}><div className="flex flex-wrap gap-1">{r.unresolved > 0 && <Badge tone="amber">{r.unresolved} to score</Badge>}<Badge tone={r.status === "final" ? "green" : "blue"}>{r.status === "final" ? "Approved" : "In review"}</Badge>{r.released && <Badge tone="purple">Released</Badge>}</div></td>
                    <td className={td}><ApplicationStatusBadge status={r.application_status} /></td>
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
