import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, TextInput, useDebounced } from "@/components/ui";
import { formatDate } from "@/utils/format";
import { EMPLOYMENT_LABELS, WORK_MODE_LABELS } from "@/utils/labels";
import type { Category, Page, PublicJob } from "@/types";

export default function JobsPage() {
  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, categoryId]);
  const { data: cats } = useQuery({ queryKey: ["categories", "active"], queryFn: async () => (await api.get<Category[]>("/job-categories")).data });
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["jobs", debounced, categoryId, page],
    queryFn: async () => (await api.get<Page<PublicJob>>("/jobs", { params: { search: debounced || undefined, category_id: categoryId || undefined, page, page_size: 12 } })).data,
  });
  return (
    <>
      <PageHeader title="Job openings" description="Find a role that fits and apply in a few clicks." />
      <div className="mb-4 flex flex-wrap gap-3">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <TextInput aria-label="Search jobs" placeholder="Search by title or keyword" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select aria-label="Filter by category" className="w-full sm:w-56" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">All categories</option>{cats?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
      </div>
      {isLoading ? <Spinner /> : error || !data ? <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card> : data.items.length === 0 ? (
        <Card><EmptyState title="No open positions right now" description={debounced || categoryId ? "Try changing your search." : "Please check back soon."} /></Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-2">
            {data.items.map((j) => (
              <Link key={j.id} to={`/jobs/${j.id}`} className="block rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-brand-300 hover:shadow">
                <div className="flex items-start justify-between gap-2"><h2 className="font-semibold text-slate-900">{j.title}</h2>{j.applied && <Badge tone="green">Applied</Badge>}</div>
                <p className="mt-1 text-sm text-slate-500">{j.category_name} · {EMPLOYMENT_LABELS[j.employment_type]} · {WORK_MODE_LABELS[j.work_mode]}{j.location ? ` · ${j.location}` : ""}</p>
                <p className="mt-3 line-clamp-2 text-sm text-slate-600">{j.description}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">{j.required_skills.slice(0, 5).map((s) => <Badge key={s} tone="blue">{s}</Badge>)}</div>
                {j.deadline && <p className="mt-3 text-xs text-slate-500">Apply by {formatDate(j.deadline)}</p>}
              </Link>
            ))}
          </div>
          <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
        </>
      )}
    </>
  );
}
