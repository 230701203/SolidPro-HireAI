import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Button, Card, Field, Spinner, Textarea, TextInput } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import type { AnalysisOverview, AnalysisReport } from "@/types";

function List({ title, items, tone }: { title: string; items: string[]; tone?: "green" | "amber" }) {
  if (!items.length) return null;
  return (
    <div>
      <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4>
      <ul className="space-y-1 text-sm text-slate-700">
        {items.map((s) => <li key={s} className="flex gap-2"><span className={tone === "green" ? "text-green-600" : tone === "amber" ? "text-amber-600" : "text-slate-400"} aria-hidden>•</span><span>{s}</span></li>)}
      </ul>
    </div>
  );
}

function Chips({ title, items, tone }: { title: string; items: string[]; tone: "green" | "red" | "blue" }) {
  if (!items.length) return null;
  return <div><h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h4><div className="flex flex-wrap gap-1.5">{items.map((s) => <Badge key={s} tone={tone}>{s}</Badge>)}</div></div>;
}

function Override({ r, onDone }: { r: AnalysisReport; onDone: () => void }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [score, setScore] = useState(String(r.override_score ?? r.ai_score ?? ""));
  const [note, setNote] = useState(r.override_note ?? "");
  const [err, setErr] = useState<string | null>(null);
  const save = useMutation({
    mutationFn: () => api.put(`/analysis/${r.id}/override`, { score: Number(score), note: note.trim() }),
    onSuccess: () => { toast.success("Reviewer score saved."); setOpen(false); onDone(); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const clear = useMutation({
    mutationFn: () => api.delete(`/analysis/${r.id}/override`),
    onSuccess: () => { toast.success("Override removed."); onDone(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const valid = score !== "" && Number(score) >= 0 && Number(score) <= 100 && note.trim().length >= 3;
  return (
    <div className="mt-4 border-t border-slate-100 pt-4">
      {!open ? (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>{r.override_score != null ? "Edit reviewer score" : "Override score"}</Button>
          {r.override_score != null && <Button size="sm" variant="ghost" loading={clear.isPending} onClick={() => clear.mutate()}>Remove override</Button>}
        </div>
      ) : (
        <div className="space-y-3">
          {err && <Alert kind="error">{err}</Alert>}
          <div className="grid gap-3 sm:grid-cols-[8rem_1fr]">
            <Field label="Your score (0-100)" htmlFor="ov-score"><TextInput id="ov-score" inputMode="numeric" value={score} onChange={(e) => setScore(e.target.value.replace(/\D/g, "").slice(0, 3))} /></Field>
            <Field label="Why are you changing it?" htmlFor="ov-note"><Textarea id="ov-note" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          </div>
          <div className="flex gap-2"><Button size="sm" loading={save.isPending} disabled={!valid} onClick={() => { setErr(null); save.mutate(); }}>Save</Button><Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button></div>
        </div>
      )}
    </div>
  );
}

function ReportView({ r, canOverride, onDone }: { r: AnalysisReport; canOverride: boolean; onDone: () => void }) {
  if (r.status === "failed") return <Alert kind="error">The analysis failed: {r.error ?? "unknown error"} You can run it again.</Alert>;
  const x = r.report!;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="text-center" aria-label={`Match score ${r.effective_score} out of 100`}>
          <p className="text-3xl font-semibold tabular-nums text-slate-900">{r.effective_score}<span className="text-base font-normal text-slate-400">/100</span></p>
          <p className="text-xs text-slate-500">{r.override_score != null ? "Reviewer score" : "AI match score"}</p>
        </div>
        {r.override_score != null && <p className="text-sm text-slate-600">AI suggested <strong>{r.ai_score}</strong>. Overridden by {r.overridden_by_name}: “{r.override_note}”</p>}
        <Badge tone={x.confidence === "high" ? "green" : x.confidence === "medium" ? "amber" : "slate"}>Confidence: {x.confidence}</Badge>
      </div>
      <p className="text-sm text-slate-700">{x.summary}</p>
      <Chips title="Required skills found" items={x.matched_required_skills} tone="green" />
      <Chips title="Required skills not found" items={x.missing_required_skills} tone="red" />
      <Chips title="Preferred skills found" items={x.matched_preferred_skills} tone="blue" />
      {x.experience_assessment && <div><h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Experience</h4><p className="text-sm text-slate-700">{x.experience_assessment}</p></div>}
      {x.education_assessment && <div><h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Education</h4><p className="text-sm text-slate-700">{x.education_assessment}</p></div>}
      <div className="grid gap-4 sm:grid-cols-2"><List title="Strengths" items={x.strengths} tone="green" /><List title="Gaps" items={x.gaps} tone="amber" /></div>
      <List title="Verify before deciding" items={x.clarifications_to_verify} tone="amber" />
      <List title="Suggested interview topics" items={x.suggested_interview_topics} />
      <p className="text-xs text-slate-500">Run by {r.requested_by_name ?? "unknown"} on {formatDateTime(r.created_at)} · resume version {r.resume_version} · {r.is_mock ? "MOCK keyword matcher" : r.model} · {r.prompt_version}</p>
      {canOverride && <Override key={`${r.id}-${r.override_score}`} r={r} onDone={onDone} />}
    </div>
  );
}

/** Advisory AI resume analysis for recruiters. Never shown to applicants and never changes the application status. */
export default function AnalysisPanel({ applicationId }: { applicationId: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ["analysis", applicationId];
  const { data, isLoading, error } = useQuery({ queryKey: key, queryFn: async () => (await api.get<AnalysisOverview>(`/applications/${applicationId}/analysis`)).data });
  const run = useMutation({
    mutationFn: () => api.post<AnalysisReport>(`/applications/${applicationId}/analysis`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: key }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const refresh = () => void qc.invalidateQueries({ queryKey: key });

  // Reviewers without the analysis permission simply do not get this panel.
  if (error) return null;
  if (isLoading || !data) return <Card className="p-5"><Spinner /></Card>;
  return (
    <Card className="p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Sparkles className="size-4 text-brand-600" aria-hidden /> AI resume analysis</h2>
        {data.can_run && <Button size="sm" variant="secondary" loading={run.isPending} disabled={!data.ai.configured} onClick={() => run.mutate()}>{data.latest ? "Run again" : "Run analysis"}</Button>}
      </div>
      <div className="mb-4 space-y-2">
        {data.ai.is_mock && <Alert kind="warning"><strong>MOCK mode.</strong> This is a simple keyword match, not real AI. Set <code>AI_PROVIDER=anthropic</code> and an API key for real analysis.</Alert>}
        {!data.ai.configured && <Alert kind="error">The configured AI provider has no API key, so analysis cannot run.</Alert>}
        <p className="text-xs text-slate-500">{data.notice}</p>
      </div>
      {data.latest ? <ReportView r={data.latest} canOverride={data.can_run} onDone={refresh} /> : <p className="text-sm text-slate-500">No analysis has been run for this application yet.</p>}
      {data.history.length > 0 && (
        <details className="mt-4 border-t border-slate-100 pt-3 text-sm">
          <summary className="cursor-pointer text-slate-600">Earlier runs ({data.history.length})</summary>
          <ul className="mt-2 space-y-1 text-slate-600">
            {data.history.map((h) => <li key={h.id}>{formatDateTime(h.created_at)} · {h.status === "failed" ? "failed" : `${h.effective_score}/100`} · {h.is_mock ? "mock" : h.model} · v{h.resume_version}</li>)}
          </ul>
        </details>
      )}
    </Card>
  );
}
