import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { OpeningStatusBadge } from "@/components/badges";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate } from "@/utils/format";
import { EMPLOYMENT_LABELS, WORK_MODE_LABELS } from "@/utils/labels";
import type { Category, OpeningListItem, Page } from "@/types";

export default function OpeningsPage() {
  const { user, hasPermission } = useAuth();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, status, categoryId]);

  const { data: cats } = useQuery({ queryKey: ["categories", "all"], queryFn: async () => (await api.get<Category[]>("/job-categories", { params: { include_inactive: true } })).data });
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["openings", debounced, status, categoryId, page],
    queryFn: async () => (await api.get<Page<OpeningListItem>>("/job-openings", { params: { search: debounced || undefined, status: status || undefined, category_id: categoryId || undefined, page, page_size: 15 } })).data,
  });

  const isAdmin = user?.role === "admin";
  return (
    <>
      <PageHeader
        title={isAdmin ? "Job openings" : "My assigned openings"}
        description={isAdmin ? "Create, publish and manage every opening." : "Openings you were assigned to or created."}
        actions={hasPermission("manage_job_openings") && <Button onClick={() => navigate("/openings/new")}><Plus className="size-4" /> New opening</Button>}
      />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search openings" placeholder="Search title or category" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by category" className="w-full sm:w-52" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">All categories</option>
            {cats?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </Select>
          <Select aria-label="Filter by status" className="w-full sm:w-44" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option><option value="draft">Draft</option><option value="published">Published</option><option value="closed">Closed</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No openings found" description={debounced || status || categoryId ? "Try changing the filters." : isAdmin ? "Create the first opening to start receiving applications." : "You have not been assigned to any openings yet."} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Opening</th><th className={th}>Status</th><th className={th}>Deadline</th><th className={th}>Applications</th><th className={th}>Assigned to</th></tr></thead>
              <tbody>
                {data.items.map((o) => (
                  <tr key={o.id} className="hover:bg-slate-50/60">
                    <td className={td}>
                      <Link to={`/openings/${o.id}`} className="font-medium text-slate-900 hover:underline">{o.title}</Link>
                      <span className="block text-xs text-slate-500">{o.category_name} · {EMPLOYMENT_LABELS[o.employment_type]} · {WORK_MODE_LABELS[o.work_mode]}</span>
                    </td>
                    <td className={td}><OpeningStatusBadge status={o.status} open={o.is_open} /></td>
                    <td className={td}>{formatDate(o.deadline)}</td>
                    <td className={`${td} tabular-nums`}>{o.applications_count}{o.pending_count > 0 && <span className="ml-1 text-xs text-amber-700">({o.pending_count} pending)</span>}</td>
                    <td className={`${td} text-slate-600`}>{o.assignees.length ? o.assignees.map((a) => a.full_name).join(", ") : <span className="text-slate-400">Unassigned</span>}</td>
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
