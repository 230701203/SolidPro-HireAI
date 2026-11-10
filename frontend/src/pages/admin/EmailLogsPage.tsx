import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Card, EmptyState, ErrorState, PageHeader, Pagination, Select, Spinner, StatusBadge, TableWrap, td, th } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import type { EmailLogEntry, Page } from "@/types";

export default function EmailLogsPage() {
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const qc = useQueryClient();
  const toast = useToast();
  useEffect(() => setPage(1), [status]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["email-logs", status, page],
    queryFn: async () => (await api.get<Page<EmailLogEntry>>("/settings/email-logs", { params: { status: status || undefined, page, page_size: 20 } })).data,
  });
  const retry = useMutation({
    mutationFn: (id: number) => api.post(`/settings/email-logs/${id}/retry`),
    onSuccess: () => { toast.success("Retry started."); setTimeout(() => void qc.invalidateQueries({ queryKey: ["email-logs"] }), 1200); void qc.invalidateQueries({ queryKey: ["email-logs"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  return (
    <>
      <PageHeader title="Email delivery" description="Every email the system sends, with its delivery status." />
      <div className="mb-4">
        <Alert kind="info"><strong>Logged (dev)</strong> means no SMTP server is configured, so the message was written to the server log and was <em>not</em> delivered. Set the SMTP variables in <code>backend/.env</code> to send real email.</Alert>
      </div>
      <Card>
        <div className="border-b border-slate-200 p-4">
          <Select aria-label="Filter by delivery status" className="w-full sm:w-56" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option><option value="sent">Sent</option><option value="failed">Failed</option><option value="queued">Queued</option><option value="dev_logged">Logged (dev)</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No emails" description="Emails appear here once the system sends them." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>When</th><th className={th}>To</th><th className={th}>Subject</th><th className={th}>Status</th><th className={th}>Attempts</th><th className={`${th} text-right`}>Actions</th></tr></thead>
              <tbody>
                {data.items.map((l) => (
                  <tr key={l.id}>
                    <td className={`${td} whitespace-nowrap`}>{formatDateTime(l.created_at)}</td>
                    <td className={td}>{l.to_email}</td>
                    <td className={td}>{l.subject}{l.error && <span className="block text-xs text-red-600">{l.error}</span>}</td>
                    <td className={td}><StatusBadge status={l.status} /></td>
                    <td className={`${td} tabular-nums`}>{l.attempts}</td>
                    <td className={`${td} text-right`}>{l.status === "failed" && <Button size="sm" variant="secondary" loading={retry.isPending && retry.variables === l.id} onClick={() => retry.mutate(l.id)}>Retry</Button>}</td>
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
