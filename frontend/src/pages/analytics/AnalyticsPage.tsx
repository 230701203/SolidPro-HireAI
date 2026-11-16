import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/services/api";
import { useAuth } from "@/contexts/AuthContext";
import { Alert, Button, Card, EmptyState, ErrorState, Field, PageHeader, Select, Spinner, TableWrap, TextInput, td, th } from "@/components/ui";
import { formatDateTime } from "@/utils/format";
import type { Analytics, OpeningListItem, Page } from "@/types";

const pct = (v: number | null) => (v == null ? "n/a" : `${v}%`);

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
      <p className="text-sm text-slate-600">{label}</p>
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </Card>
  );
}

function ChartCard({ title, empty, children }: { title: string; empty: boolean; children: ReactNode }) {
  return (
    <Card className="p-4 break-inside-avoid">
      <h2 className="mb-3 font-semibold text-slate-900">{title}</h2>
      {empty ? <p className="py-10 text-center text-sm text-slate-500">No data for these filters.</p> : <div className="h-64">{children}</div>}
    </Card>
  );
}

export default function AnalyticsPage() {
  const { user } = useAuth();
  const [f, setF] = useState({ date_from: "", date_to: "", opening_id: "", category_id: "", employee_id: "" });
  const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== ""));
  const openings = useQuery({ queryKey: ["openings-filter"], queryFn: async () => (await api.get<Page<OpeningListItem>>("/job-openings", { params: { page_size: 100 } })).data });
  const cats = useQuery({ queryKey: ["categories-filter"], queryFn: async () => (await api.get<{ id: number; name: string }[]>("/job-categories")).data });
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["analytics", params], queryFn: async () => (await api.get<Analytics>("/analytics/recruitment", { params })).data });
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });
  const link = (report: string, format: string) => `/api/analytics/export?${new URLSearchParams({ ...params, report, format }).toString()}`;

  return (
    <>
      <PageHeader title="Recruitment analytics" description="Every figure is calculated from real records you are allowed to see. Rates state their denominators; small samples are not meaningful."
        actions={<Button variant="secondary" onClick={() => window.print()}>Print / save as PDF</Button>} />
      <Card className="mb-4 p-4 print:hidden">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <Field label="From" htmlFor="an-from"><TextInput id="an-from" type="date" value={f.date_from} onChange={set("date_from")} /></Field>
          <Field label="To" htmlFor="an-to"><TextInput id="an-to" type="date" value={f.date_to} onChange={set("date_to")} /></Field>
          <Field label="Opening" htmlFor="an-op"><Select id="an-op" value={f.opening_id} onChange={set("opening_id")}><option value="">All openings</option>{openings.data?.items.map((o) => <option key={o.id} value={o.id}>{o.title}</option>)}</Select></Field>
          <Field label="Category" htmlFor="an-cat"><Select id="an-cat" value={f.category_id} onChange={set("category_id")}><option value="">All categories</option>{cats.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select></Field>
          {user?.role === "admin" && <Field label="Employee (assigned)" htmlFor="an-emp"><TextInput id="an-emp" inputMode="numeric" placeholder="Employee id" value={f.employee_id} onChange={set("employee_id")} /></Field>}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <span className="text-slate-500">Export:</span>
          {[["openings", "Per opening"], ["categories", "Per category"], ["monthly", "Monthly"], ["funnel", "Funnel"]].map(([r, l]) => (
            <span key={r} className="space-x-1">{l}: <a className="text-brand-700 hover:underline" href={link(r, "csv")}>CSV</a> <a className="text-brand-700 hover:underline" href={link(r, "xlsx")}>XLSX</a></span>
          ))}
        </div>
      </Card>
      {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.totals.applications === 0 ? (
        <EmptyState title="No applications match" description="Change the filters, or wait for applications to arrive." />
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Applications" value={data.totals.applications} hint={`${data.totals.openings_in_scope} opening(s) in scope`} />
            <Stat label="Pending review" value={data.totals.pending} />
            <Stat label="Approval rate" value={pct(data.rates.approval_rate)} hint={`of ${data.denominators.decided} decided`} />
            <Stat label="Rejection rate" value={pct(data.rates.rejection_rate)} hint={`of ${data.denominators.decided} decided`} />
            <Stat label="Test completion" value={pct(data.rates.completion_rate)} hint={`of ${data.denominators.scheduled} scheduled`} />
            <Stat label="Attendance" value={pct(data.rates.attendance_rate)} hint={`of ${data.denominators.attended_or_missed} attended or missed`} />
            <Stat label="Shortlisting rate" value={pct(data.rates.shortlisting_rate)} hint={`of ${data.denominators.evaluated} evaluated`} />
            <Stat label="Selection rate" value={pct(data.rates.selection_rate)} hint={`of ${data.denominators.shortlisted} shortlisted`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Hiring funnel" empty={false}>
              <ResponsiveContainer><BarChart data={data.funnel} layout="vertical" margin={{ left: 30 }}><CartesianGrid strokeDasharray="3 3" /><XAxis type="number" allowDecimals={false} /><YAxis type="category" dataKey="stage" width={150} tick={{ fontSize: 12 }} /><Tooltip /><Bar dataKey="count" fill="#1d4ed8" /></BarChart></ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Applications per month" empty={data.applications_by_month.length === 0}>
              <ResponsiveContainer><BarChart data={data.applications_by_month}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="#0f766e" name="Applications" /></BarChart></ResponsiveContainer>
            </ChartCard>
            <ChartCard title={`Test score distribution (${data.scores.evaluated_candidates} evaluated, avg ${pct(data.scores.average_percentage)})`} empty={data.scores.evaluated_candidates === 0}>
              <ResponsiveContainer><BarChart data={data.scores.distribution}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="range" /><YAxis allowDecimals={false} /><Tooltip /><Bar dataKey="count" fill="#7c3aed" name="Candidates" /></BarChart></ResponsiveContainer>
            </ChartCard>
            <ChartCard title={`Average match score by month (${data.match_scores.analysed} analysed, advisory)`} empty={data.match_scores.trend.length === 0}>
              <ResponsiveContainer><LineChart data={data.match_scores.trend}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="month" /><YAxis domain={[0, 100]} /><Tooltip /><Line dataKey="average" stroke="#b45309" name="Average" /></LineChart></ResponsiveContainer>
            </ChartCard>
          </div>
          <Card>
            <h2 className="border-b border-slate-200 px-4 py-3 font-semibold">By opening</h2>
            <TableWrap>
              <thead><tr><th className={th}>Opening</th><th className={th}>Applications</th><th className={th}>Approved</th><th className={th}>Rejected</th><th className={th}>Shortlisted</th><th className={th}>Selected</th></tr></thead>
              <tbody>{data.per_opening.map((r) => <tr key={r.id}><td className={td}>{r.name}</td><td className={`${td} tabular-nums`}>{r.applications}</td><td className={`${td} tabular-nums`}>{r.approved}</td><td className={`${td} tabular-nums`}>{r.rejected}</td><td className={`${td} tabular-nums`}>{r.shortlisted}</td><td className={`${td} tabular-nums`}>{r.selected}</td></tr>)}</tbody>
            </TableWrap>
          </Card>
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="p-4"><h2 className="mb-2 font-semibold">Most common skill gaps</h2>{data.match_scores.top_missing_skills.length === 0 ? <p className="text-sm text-slate-500">No analysed resumes yet.</p> : <ul className="space-y-1 text-sm">{data.match_scores.top_missing_skills.map((s) => <li key={s.skill} className="flex justify-between"><span>{s.skill}</span><span className="tabular-nums text-slate-500">{s.count}</span></li>)}</ul>}</Card>
            <Card className="p-4"><h2 className="mb-2 font-semibold">Most common matched skills</h2>{data.match_scores.top_matched_skills.length === 0 ? <p className="text-sm text-slate-500">No analysed resumes yet.</p> : <ul className="space-y-1 text-sm">{data.match_scores.top_matched_skills.map((s) => <li key={s.skill} className="flex justify-between"><span>{s.skill}</span><span className="tabular-nums text-slate-500">{s.count}</span></li>)}</ul>}</Card>
            <Card className="p-4"><h2 className="mb-2 font-semibold">Average time between stages</h2><ul className="space-y-1 text-sm">{data.stage_durations.map((d) => <li key={d.stage} className="flex justify-between"><span>{d.stage}</span><span className="tabular-nums text-slate-500">{d.avg_days != null ? `${d.avg_days} d (n=${d.sample})` : "n/a"}</span></li>)}</ul></Card>
          </div>
          <Alert kind="info"><strong>How these are calculated.</strong> <ul className="mt-1 list-disc pl-5">{data.notes.map((n) => <li key={n}>{n}</li>)}</ul><p className="mt-1 text-xs">Generated {formatDateTime(data.generated_at)}.</p></Alert>
        </div>
      )}
    </>
  );
}
