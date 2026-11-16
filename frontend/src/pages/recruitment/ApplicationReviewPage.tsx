import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Button, Card, ErrorState, Field, Modal, PageHeader, Spinner, Textarea } from "@/components/ui";
import { ApplicationStatusBadge } from "@/components/badges";
import Timeline from "@/components/Timeline";
import ProfileView from "@/components/ProfileView";
import ResumeLinks from "@/components/ResumeLinks";
import AnalysisPanel from "@/components/AnalysisPanel";
import AssessmentCard from "@/components/AssessmentCard";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import type { ApplicationDetail } from "@/types";

type Dialog = "approve" | "reject" | "info" | "comment" | null;
const CFG = {
  approve: { title: "Approve application", path: "approve", field: "note", label: "Note to applicant (optional)", required: false, button: "Approve" },
  reject: { title: "Reject application", path: "reject", field: "reason", label: "Reason (shared with the applicant)", required: true, button: "Reject" },
  info: { title: "Request more information", path: "request-info", field: "message", label: "What do you need from the applicant?", required: true, button: "Send request" },
  comment: { title: "Add internal comment", path: "comment", field: "message", label: "Comment (hidden from the applicant)", required: true, button: "Add comment" },
} as const;

function ActionDialog({ kind, id, onClose }: { kind: Exclude<Dialog, null>; id: string; onClose: () => void }) {
  const c = CFG[kind];
  const qc = useQueryClient();
  const toast = useToast();
  const [text, setText] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const m = useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>(`/applications/${id}/${c.path}`, { [c.field]: c.required ? text.trim() : text.trim() || null })).data,
    onSuccess: (d) => { qc.setQueryData(["application", id], d); void qc.invalidateQueries({ queryKey: ["applications"] }); toast.success("Saved."); onClose(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const invalid = c.required && text.trim().length < 3;
  return (
    <Modal open onClose={onClose} title={c.title}
      footer={<><Button variant="secondary" onClick={onClose} disabled={m.isPending}>Cancel</Button><Button variant={kind === "reject" ? "danger" : "primary"} loading={m.isPending} disabled={invalid} onClick={() => { setErr(null); m.mutate(); }}>{c.button}</Button></>}>
      <div className="space-y-3">
        {kind === "approve" && <Alert kind="info">Approval is final and the applicant is notified. AI scores never decide this: you do.</Alert>}
        {kind === "reject" && <Alert kind="warning">Rejection is final and the applicant is notified with your reason.</Alert>}
        {err && <Alert kind="error">{err}</Alert>}
        <Field label={c.label} htmlFor="action-text"><Textarea id="action-text" rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}

export default function ApplicationReviewPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const toast = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const { data: a, isLoading, error, refetch } = useQuery({ queryKey: ["application", id], queryFn: async () => (await api.get<ApplicationDetail>(`/applications/${id}`)).data });
  const start = useMutation({
    mutationFn: async () => (await api.post<ApplicationDetail>(`/applications/${id}/start-review`)).data,
    onSuccess: (d) => { qc.setQueryData(["application", id], d); void qc.invalidateQueries({ queryKey: ["applications"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (isLoading) return <Spinner />;
  if (error || !a) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const final = ["approved", "rejected", "withdrawn"].includes(a.status);
  return (
    <>
      <PageHeader title={a.candidate_name} description={`Applied for ${a.opening_title} · ${formatDateTime(a.submitted_at)}`}
        actions={<Link to="/applications" className="text-sm text-brand-700 hover:underline">← All applications</Link>} />
      <div className="mb-4 flex flex-wrap items-center gap-3"><ApplicationStatusBadge status={a.status} />
        {a.can_review && !final && (
          <div className="flex flex-wrap gap-2">
            {a.status === "submitted" && <Button size="sm" loading={start.isPending} onClick={() => start.mutate()}>Start review</Button>}
            {a.status !== "submitted" && <><Button size="sm" onClick={() => setDialog("approve")}>Approve</Button><Button size="sm" variant="danger" onClick={() => setDialog("reject")}>Reject</Button></>}
            {a.status === "under_review" && <Button size="sm" variant="secondary" onClick={() => setDialog("info")}>Request info</Button>}
          </div>
        )}
        {a.can_review && <Button size="sm" variant="ghost" onClick={() => setDialog("comment")}>Add internal comment</Button>}
      </div>
      {final && a.decision_reason && <div className="mb-4"><Alert kind={a.status === "approved" ? "success" : "info"}>Decision by {a.decided_by_name ?? "reviewer"}: {a.decision_reason}</Alert></div>}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {a.cover_note && <Card className="p-5"><h2 className="mb-2 font-semibold text-slate-900">Cover note</h2><p className="whitespace-pre-line text-sm text-slate-700">{a.cover_note}</p></Card>}
          <Card className="p-5"><h2 className="mb-2 font-semibold text-slate-900">Resume submitted</h2><ResumeLinks resume={a.resume} /><p className="mt-1 text-xs text-slate-500">This is the exact version attached when the applicant applied.</p></Card>
          {a.status === "approved" && <AssessmentCard applicationId={a.id} />}
          <AnalysisPanel applicationId={id} />
          {a.candidate && <ProfileView p={a.candidate} />}
        </div>
        <Card className="h-fit p-5"><h2 className="mb-3 font-semibold text-slate-900">History</h2><Timeline items={a.history} staff /></Card>
      </div>
      {dialog && <ActionDialog kind={dialog} id={id} onClose={() => setDialog(null)} />}
    </>
  );
}
