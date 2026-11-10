import { Fragment, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Card, EmptyState, ErrorState, PageHeader, Pagination, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { formatDateTime } from "@/utils/format";
import type { AuditLogEntry, Page } from "@/types";

export default function AuditLogsPage() {
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, from, to]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit-logs", debounced, from, to, page],
    queryFn: async () => (await api.get<Page<AuditLogEntry>>("/audit-logs", { params: { search: debounced || undefined, date_from: from || undefined, date_to: to || undefined, page, page_size: 25 } })).data,
  });

  return (
    <>
      <PageHeader title="Audit logs" description="A read-only record of security-relevant actions." />
      <Card>
        <div className="flex flex-wrap items-end gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search audit logs" placeholder="Search action, name or email" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <label className="text-xs text-slate-500">From<TextInput type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} /></label>
          <label className="text-xs text-slate-500">To<TextInput type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} /></label>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No audit entries" description="Nothing matches these filters." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={`${th} w-8`} /><th className={th}>When</th><th className={th}>Actor</th><th className={th}>Action</th><th className={th}>Target</th><th className={th}>IP</th></tr></thead>
              <tbody>
                {data.items.map((a) => (
                  <Fragment key={a.id}>
                    <tr className="cursor-pointer hover:bg-slate-50/60" onClick={() => setOpen(open === a.id ? null : a.id)}>
                      <td className={td}>{a.details ? (open === a.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />) : null}</td>
                      <td className={`${td} whitespace-nowrap`}>{formatDateTime(a.created_at)}</td>
                      <td className={td}>{a.actor_name ?? <span className="text-slate-400">System / anonymous</span>}{a.actor_email && <span className="block text-xs text-slate-500">{a.actor_email}</span>}</td>
                      <td className={`${td} font-mono text-xs`}>{a.action}</td>
                      <td className={td}>{a.entity_type ? `${a.entity_type} #${a.entity_id}` : "—"}</td>
                      <td className={`${td} text-xs text-slate-500`}>{a.ip_address ?? "—"}</td>
                    </tr>
                    {open === a.id && a.details && (
                      <tr><td /><td colSpan={5} className="border-b border-slate-100 bg-slate-50 px-4 py-3"><pre className="overflow-x-auto text-xs text-slate-700">{JSON.stringify(a.details, null, 2)}</pre></td></tr>
                    )}
                  </Fragment>
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
