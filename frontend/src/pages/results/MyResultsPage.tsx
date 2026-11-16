import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Alert, Card, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { formatDateTime } from "@/utils/format";
import type { MyResult } from "@/types";

function Result({ r }: { r: MyResult }) {
  return (
    <Card className="p-5">
      <h2 className="text-base font-semibold text-slate-900">{r.opening_title}</h2>
      <p className="text-xs text-slate-500">{r.assessment_title} · taken {formatDateTime(r.test_date)} · released {formatDateTime(r.released_at)}</p>
      <p className="mt-4 text-3xl font-semibold tabular-nums text-slate-900">{r.total_obtained}<span className="text-lg font-normal text-slate-500"> / {r.total_marks}</span>{r.percentage != null && <span className="ml-3 text-lg text-slate-600">{r.percentage}%</span>}</p>
      <ul className="mt-4 divide-y divide-slate-100 text-sm">
        {r.sections.map((s) => <li key={s.kind} className="flex justify-between py-2"><span>{s.title}</span><span className="tabular-nums">{s.obtained} / {s.total}</span></li>)}
      </ul>
      {r.time_taken_seconds != null && <p className="mt-3 text-xs text-slate-500">Time taken: {Math.floor(r.time_taken_seconds / 60)} min {r.time_taken_seconds % 60} s</p>}
      {r.feedback && <div className="mt-4 rounded-md bg-slate-50 p-3 text-sm text-slate-700"><strong className="block text-slate-900">Feedback from the recruitment team</strong><span className="whitespace-pre-wrap">{r.feedback}</span></div>}
      <p className="mt-4 text-xs text-slate-500">Your speaking score is an automated measure that was checked by a reviewer; accent is not penalised. This result is one input into the hiring process. People at SolidPro make the decisions.</p>
    </Card>
  );
}

export default function MyResultsPage() {
  const { id } = useParams();
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["my-results"], queryFn: async () => (await api.get<MyResult[]>("/my-results")).data });
  if (isLoading) return <Spinner />;
  if (error || !data) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;
  const shown = id ? data.filter((r) => r.id === Number(id)) : data;
  return (
    <>
      <PageHeader title="My results" description="Results the recruitment team has released to you." actions={id ? <Link to="/my-results" className="text-sm text-brand-700 hover:underline">← All results</Link> : undefined} />
      {id && shown.length === 0 && <Alert kind="warning">That result is not available.</Alert>}
      {!id && data.length === 0 ? <Card><EmptyState title="No released results" description="Results appear here after the team has reviewed and released them. You will be notified." /></Card> : <div className="space-y-4">{shown.map((r) => (id ? <Result key={r.id} r={r} /> : <Link key={r.id} to={`/my-results/${r.id}`} className="block"><Result r={r} /></Link>))}</div>}
    </>
  );
}
