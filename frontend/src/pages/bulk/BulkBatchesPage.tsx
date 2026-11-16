import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Modal, PageHeader, Pagination, Select, Spinner, TableWrap, TextInput, td, th } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import type { BulkBatch, BulkCreated, OpeningListItem, Page } from "@/types";

const MAX_FILES = 50;

function UploadDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [openingId, setOpeningId] = useState("");
  const [name, setName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<BulkCreated["rejected"]>([]);
  const openings = useQuery({ queryKey: ["openings-for-bulk"], enabled: open, queryFn: async () => (await api.get<Page<OpeningListItem>>("/job-openings", { params: { page_size: 100 } })).data });
  const upload = useMutation({
    mutationFn: async () => {
      const fd = new FormData();
      fd.append("opening_id", openingId);
      fd.append("name", name);
      files.forEach((f) => fd.append("files", f));
      return (await api.post<BulkCreated>("/bulk-batches", fd)).data;
    },
    onSuccess: (res) => {
      void qc.invalidateQueries({ queryKey: ["bulk-batches"] });
      if (res.rejected.length) { setRejected(res.rejected); toast.success(`Uploaded with ${res.rejected.length} file(s) skipped.`); }
      else toast.success("Upload received. Processing has started.");
      nav(`/bulk/${res.batch.id}`);
    },
  });
  const tooMany = files.length > MAX_FILES;
  const submit = (e: FormEvent) => { e.preventDefault(); if (openingId && files.length && !tooMany) upload.mutate(); };
  return (
    <Modal open={open} onClose={onClose} title="Upload resumes in bulk" footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button type="submit" form="bulk-upload-form" loading={upload.isPending} disabled={!openingId || files.length === 0 || tooMany}>Upload and screen</Button>
    </>}>
      <form id="bulk-upload-form" onSubmit={submit} className="space-y-4">
        <Alert kind="info">Screening only. Nothing here creates accounts or changes any applicant. People in a batch have not applied, so they are never notified.</Alert>
        {upload.isError && <Alert kind="error">{errorMessage(upload.error)}</Alert>}
        <Field label="Job opening" htmlFor="bulk-opening">
          <Select id="bulk-opening" value={openingId} onChange={(e) => setOpeningId(e.target.value)}>
            <option value="">Select an opening…</option>
            {openings.data?.items.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}
          </Select>
        </Field>
        <Field label="Batch name (optional)" htmlFor="bulk-name"><TextInput id="bulk-name" value={name} maxLength={150} onChange={(e) => setName(e.target.value)} placeholder="e.g. Campus drive, Nov 2026" /></Field>
        <Field label="Resumes (PDF or DOCX)" htmlFor="bulk-files" hint={`Up to ${MAX_FILES} files per batch, 5 MB each by default.`} error={tooMany ? `Choose at most ${MAX_FILES} files.` : undefined}>
          <input id="bulk-files" type="file" multiple accept=".pdf,.docx" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} className="block w-full text-sm" />
        </Field>
        {files.length > 0 && <p className="text-sm text-slate-600">{files.length} file(s) selected.</p>}
        {rejected.length > 0 && <Alert kind="warning">{rejected.map((r) => `${r.filename}: ${r.reason}`).join(" · ")}</Alert>}
      </form>
    </Modal>
  );
}

export default function BulkBatchesPage() {
  const [page, setPage] = useState(1);
  const [show, setShow] = useState(false);
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["bulk-batches", page], queryFn: async () => (await api.get<Page<BulkBatch>>("/bulk-batches", { params: { page, page_size: 15 } })).data });
  return (
    <>
      <PageHeader title="Bulk resume screening" description="Screen many resumes against an opening at once. Results are advisory and extracted details are best-effort guesses: always check the resume itself."
        actions={<Button onClick={() => setShow(true)}>Upload resumes</Button>} />
      <Card>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No batches yet" description="Upload a set of resumes to rank them against a job opening." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Batch</th><th className={th}>Opening</th><th className={th}>Progress</th><th className={th}>Created</th></tr></thead>
              <tbody>
                {data.items.map((b) => (
                  <tr key={b.id} className="hover:bg-slate-50/60">
                    <td className={td}><Link to={`/bulk/${b.id}`} className="font-medium text-slate-900 hover:underline">{b.name}</Link>{b.ai_is_mock && <Badge tone="amber">MOCK AI</Badge>}</td>
                    <td className={td}>{b.opening_title}</td>
                    <td className={`${td} text-sm tabular-nums`}>{b.progress.complete ? "Complete" : "Processing"} · {b.progress.finished}/{b.progress.total}{b.progress.failed > 0 && <span className="ml-1 text-red-700">({b.progress.failed} failed)</span>}</td>
                    <td className={`${td} text-sm`}>{formatDateTime(b.created_at)}{b.created_by_name && <span className="block text-xs text-slate-500">{b.created_by_name}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
      <UploadDialog open={show} onClose={() => setShow(false)} />
    </>
  );
}
