import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Modal, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th, useDebounced } from "@/components/ui";
import { useToast } from "@/components/Toast";
import type { BulkBatch, BulkItem, BulkItemDetail, Page } from "@/types";

const DUP: Record<string, string> = {
  existing_applicant: "Registered applicant",
  duplicate_in_batch: "Same email in batch",
  duplicate_file: "Same file in batch",
};
const REVIEW_LABEL = { unreviewed: "Unreviewed", interesting: "Interesting", not_suitable: "Not suitable" } as const;

function ItemDialog({ id, onClose }: { id: number; onClose: () => void }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["bulk-item", id], queryFn: async () => (await api.get<BulkItemDetail>(`/bulk-items/${id}`)).data });
  const a = (data?.analysis ?? {}) as Record<string, unknown>;
  const list = (k: string) => (Array.isArray(a[k]) ? (a[k] as string[]) : []);
  return (
    <Modal open onClose={onClose} title={data?.candidate_name ?? data?.filename ?? "Resume"} wide footer={<>
      <a href={`/api/bulk-items/${id}/file`} target="_blank" rel="noopener noreferrer" className="text-sm font-medium text-brand-700 hover:underline">Open resume file</a>
      <Button variant="secondary" onClick={onClose}>Close</Button>
    </>}>
      {isLoading ? <Spinner /> : error || !data ? <Alert kind="error">{errorMessage(error)}</Alert> : (
        <div className="space-y-4 text-sm">
          <Alert kind="info">Name, contact details, skills and experience below were guessed from the resume text. Verify them against the file.</Alert>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
            <dt className="text-slate-500">Email</dt><dd>{data.email ?? "—"}</dd>
            <dt className="text-slate-500">Phone</dt><dd>{data.phone ?? "—"}</dd>
            <dt className="text-slate-500">Experience</dt><dd>{data.experience_years != null ? `${data.experience_years} years` : "Not stated"}</dd>
            <dt className="text-slate-500">Education</dt><dd>{data.education.length ? data.education.join("; ") : "—"}</dd>
            <dt className="text-slate-500">Skills found</dt><dd>{data.skills.join(", ") || "—"}</dd>
          </dl>
          {data.analysis && (
            <div className="space-y-2 rounded-lg border border-slate-200 p-3">
              <p className="font-medium">Match score {data.match_score}/100 {a.mock ? <Badge tone="amber">MOCK AI</Badge> : null}</p>
              <p>{String(a.summary ?? "")}</p>
              <p><span className="text-slate-500">Matched required: </span>{list("matched_required_skills").join(", ") || "none"}</p>
              <p><span className="text-slate-500">Missing required: </span>{list("missing_required_skills").join(", ") || "none"}</p>
              {list("clarifications_to_verify").length > 0 && <p><span className="text-slate-500">To verify: </span>{list("clarifications_to_verify").join("; ")}</p>}
            </div>
          )}
          {data.warnings.length > 0 && <ul className="list-disc pl-5 text-amber-800">{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
          {data.error && <Alert kind="error">{data.error}</Alert>}
        </div>
      )}
    </Modal>
  );
}

export default function BulkBatchDetailPage() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [review, setReview] = useState("");
  const [dups, setDups] = useState("");
  const [sort, setSort] = useState("score");
  const [desc, setDesc] = useState(true);
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const debounced = useDebounced(search);
  useEffect(() => setPage(1), [debounced, status, review, dups, sort, desc]);

  const batch = useQuery({
    queryKey: ["bulk-batch", id],
    queryFn: async () => (await api.get<BulkBatch>(`/bulk-batches/${id}`)).data,
    refetchInterval: (q) => (q.state.data && !q.state.data.progress.complete ? 2000 : false),
  });
  const complete = batch.data?.progress.complete ?? false;
  const params = { search: debounced || undefined, status: status || undefined, review_status: review || undefined, duplicates: dups === "" ? undefined : dups === "yes", sort, desc, page, page_size: 20 };
  const items = useQuery({
    queryKey: ["bulk-items", id, params, complete, batch.data?.progress.finished],
    enabled: !!batch.data,
    queryFn: async () => (await api.get<Page<BulkItem>>(`/bulk-batches/${id}/items`, { params })).data,
  });
  const triage = useMutation({
    mutationFn: async (v: { itemId: number; status: string }) => (await api.put(`/bulk-items/${v.itemId}/triage`, { status: v.status })).data,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["bulk-items", id] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const retry = useMutation({
    mutationFn: async () => (await api.post<{ requeued: number }>(`/bulk-batches/${id}/retry`)).data,
    onSuccess: (r) => { toast.success(`${r.requeued} file(s) queued again.`); void qc.invalidateQueries({ queryKey: ["bulk-batch", id] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const del = useMutation({
    mutationFn: async () => api.delete(`/bulk-batches/${id}`),
    onSuccess: () => { toast.success("Batch and its files were deleted."); void qc.invalidateQueries({ queryKey: ["bulk-batches"] }); nav("/bulk"); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (batch.isLoading) return <Spinner />;
  if (batch.error || !batch.data) return <ErrorState message={errorMessage(batch.error)} onRetry={() => void batch.refetch()} />;
  const b = batch.data;
  const p = b.progress;
  const pct = p.total ? Math.round((100 * p.finished) / p.total) : 0;
  const sortBy = (k: string) => { if (sort === k) setDesc(!desc); else { setSort(k); setDesc(k === "score"); } };
  const arrow = (k: string) => (sort === k ? (desc ? " ↓" : " ↑") : "");

  return (
    <>
      <PageHeader title={b.name} description={`Screened against ${b.opening_title}. Scores are advisory; triage labels here do not affect any applicant.`}
        actions={<>
          <a className="text-sm font-medium text-brand-700 hover:underline self-center" href={`/api/bulk-batches/${b.id}/export?format=csv`}>Export CSV</a>
          <a className="text-sm font-medium text-brand-700 hover:underline self-center" href={`/api/bulk-batches/${b.id}/export?format=xlsx`}>Export XLSX</a>
          <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>Delete batch</Button>
        </>} />
      <p className="mb-3 text-sm"><Link to="/bulk" className="text-brand-700 hover:underline">← All batches</Link></p>
      {b.ai_is_mock && <div className="mb-3"><Alert kind="warning">MOCK AI: scores come from a simple keyword matcher, not a real model. Use them only to order the list.</Alert></div>}
      <Card className="mb-4 p-4">
        <div className="mb-2 flex items-center justify-between text-sm">
          <span>{complete ? "Processing complete" : "Processing…"} {p.finished}/{p.total}</span>
          {p.failed > 0 && <Button size="sm" variant="secondary" loading={retry.isPending} onClick={() => retry.mutate()}>Retry {p.failed} failed</Button>}
        </div>
        <div className="h-2 overflow-hidden rounded bg-slate-100" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Batch progress"><div className="h-full bg-brand-600 transition-all" style={{ width: `${pct}%` }} /></div>
      </Card>
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search resumes" placeholder="Search name, email or file" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by processing status" className="w-40" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Any status</option><option value="done">Done</option><option value="failed">Failed</option><option value="queued">Queued</option></Select>
          <Select aria-label="Filter by triage" className="w-44" value={review} onChange={(e) => setReview(e.target.value)}><option value="">Any triage</option>{Object.entries(REVIEW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
          <Select aria-label="Filter duplicates" className="w-44" value={dups} onChange={(e) => setDups(e.target.value)}><option value="">All resumes</option><option value="yes">Duplicates only</option><option value="no">Hide duplicates</option></Select>
        </div>
        {items.isLoading ? <Spinner /> : items.error || !items.data ? <ErrorState message={errorMessage(items.error)} onRetry={() => void items.refetch()} /> : items.data.items.length === 0 ? (
          <EmptyState title="No resumes match" description="Try changing the filters." />
        ) : (
          <>
            <TableWrap>
              <thead><tr>
                <th className={th}><button onClick={() => sortBy("name")}>Candidate{arrow("name")}</button></th>
                <th className={th}><button onClick={() => sortBy("score")}>Match{arrow("score")}</button></th>
                <th className={th}><button onClick={() => sortBy("experience")}>Experience{arrow("experience")}</button></th>
                <th className={th}>Flags</th><th className={th}>Triage</th>
              </tr></thead>
              <tbody>
                {items.data.items.map((r) => (
                  <tr key={r.id} className="hover:bg-slate-50/60">
                    <td className={td}>
                      <button onClick={() => setOpen(r.id)} className="text-left font-medium text-slate-900 hover:underline">{r.candidate_name ?? r.filename}</button>
                      <span className="block text-xs text-slate-500">{r.email ?? r.filename}</span>
                    </td>
                    <td className={`${td} tabular-nums`}>{r.status === "done" ? (r.match_score ?? "—") : r.status === "failed" ? <Badge tone="red">Failed</Badge> : <Badge tone="blue">{r.status}</Badge>}</td>
                    <td className={`${td} tabular-nums`}>{r.experience_years != null ? `${r.experience_years} y` : "—"}</td>
                    <td className={td}><div className="flex flex-wrap gap-1">
                      {r.duplicate_kind && <Badge tone="amber">{DUP[r.duplicate_kind]}</Badge>}
                      {r.existing_application_id && <Link to={`/applications/${r.existing_application_id}`} className="text-xs text-brand-700 hover:underline">Open their application</Link>}
                      {r.warnings.length > 0 && <Badge tone="slate">{r.warnings.length} note(s)</Badge>}
                    </div></td>
                    <td className={td}>
                      <Select aria-label={`Triage for ${r.candidate_name ?? r.filename}`} className="w-36" value={r.review_status} onChange={(e) => triage.mutate({ itemId: r.id, status: e.target.value })}>
                        {Object.entries(REVIEW_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                      </Select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={items.data.page} pages={items.data.pages} total={items.data.total} pageSize={items.data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
      {open != null && <ItemDialog id={open} onClose={() => setOpen(null)} />}
      <ConfirmDialog open={confirmDelete} danger onCancel={() => setConfirmDelete(false)} title="Delete this batch?" message="All resumes and results in this batch are permanently removed. This cannot be undone." confirmLabel="Delete batch" onConfirm={() => del.mutate()} loading={del.isPending} />
    </>
  );
}
