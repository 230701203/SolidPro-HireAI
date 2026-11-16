import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Card, ConfirmDialog, ErrorState, Field, PageHeader, Spinner, Textarea } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import Timeline from "@/components/Timeline";
import ResumeLinks from "@/components/ResumeLinks";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import type { ApplicationDetail } from "@/types";

export default function MyApplicationDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const { data: a, isLoading, error, refetch } = useQuery({ queryKey: ["application", id], queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${id}`)).data });
  const done = (d: ApplicationDetail, text: string) => { qc.setQueryData(["application", id], d); void qc.invalidateQueries({ queryKey: ["my-applications"] }); toast.success(text); };
  const withdraw = useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>(`/applications/${id}/withdraw`)).data,
    onSuccess: (d) => { setConfirm(false); done(d, "Application withdrawn."); },
    onError: (e) => { setConfirm(false); toast.error(errorMessage(e)); },
  });
  const respond = useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>(`/applications/${id}/respond`, { message: msg.trim() })).data,
    onSuccess: (d) => { setMsg(""); done(d, "Response sent."); },
    onError: (e) => setErr(errorMessage(e)),
  });
  if (isLoading) return <Spinner />;
  if (error || !a) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const final = ["approved", "rejected", "withdrawn"].includes(a.status);
  return (
    <>
      <PageHeader title={a.opening_title} description={`${a.category_name} · applied ${formatDateTime(a.submitted_at)}`} actions={<Link to="/my-applications" className="text-sm text-brand-700 hover:underline">← My applications</Link>} />
      <div className="mb-4 flex items-center gap-3"><ApplicationStatusBadge status={a.status} />{!final && <Button size="sm" variant="secondary" onClick={() => setConfirm(true)}>Withdraw</Button>}</div>
      {a.status === "approved" && <div className="mb-4"><Alert kind="success">Your application was approved. {a.decision_reason}</Alert></div>}
      {a.status === "rejected" && <div className="mb-4"><Alert kind="info">Your application was not selected. {a.decision_reason}</Alert></div>}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {a.status === "info_requested" && (
            <Card className="space-y-3 p-5">
              <h2 className="font-semibold text-slate-900">The recruitment team needs more information</h2>
              {err && <Alert kind="error">{err}</Alert>}
              <Field label="Your response" htmlFor="respond"><Textarea id="respond" rows={4} maxLength={2000} value={msg} onChange={(e) => setMsg(e.target.value)} /></Field>
              <Button loading={respond.isPending} disabled={msg.trim().length < 3} onClick={() => { setErr(null); respond.mutate(); }}>Send response</Button>
            </Card>
          )}
          {a.cover_note && <Card className="p-5"><h2 className="mb-2 font-semibold text-slate-900">Your cover note</h2><p className="whitespace-pre-line text-sm text-slate-700">{a.cover_note}</p></Card>}
          <Card className="p-5"><h2 className="mb-2 font-semibold text-slate-900">Resume submitted</h2><ResumeLinks resume={a.resume} /></Card>
        </div>
        <Card className="h-fit p-5"><h2 className="mb-3 font-semibold text-slate-900">Progress</h2><Timeline items={a.history} /></Card>
      </div>
      <ConfirmDialog open={confirm} title="Withdraw application?" message="The recruitment team will be told. This cannot be undone." confirmLabel="Withdraw" danger loading={withdraw.isPending} onCancel={() => setConfirm(false)} onConfirm={() => withdraw.mutate()} />
    </>
  );
}
