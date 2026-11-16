import { useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/services/api";
import { Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { formatDateTime } from "@/utils/format";
import { INTERVIEW_TONE } from "./InterviewsPage";
import type { MyInterview } from "@/types";

export default function MyInterviewsPage() {
  const { data, isLoading, error, refetch } = useQuery({ queryKey: ["my-interviews"], queryFn: async () => (await api.get<MyInterview[]>("/my-interviews")).data });
  return (
    <>
      <PageHeader title="My interviews" description="Interviews arranged for your applications." />
      {isLoading ? <Spinner /> : error || !data ? <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card> : data.length === 0 ? (
        <Card><EmptyState title="No interviews yet" description="If you are shortlisted, the recruitment team will arrange an interview and you will be notified here and by email." /></Card>
      ) : (
        <ul className="space-y-3">
          {data.map((i) => (
            <li key={i.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-medium text-slate-900">{i.opening_title}</span><Badge tone={INTERVIEW_TONE[i.status]}>{i.status}</Badge></div>
              <p className="mt-1 text-sm text-slate-600 capitalize">{i.interview_type} interview · {i.mode} · {i.duration_minutes} minutes</p>
              <p className="mt-1 text-sm text-slate-800">{i.scheduled_start ? formatDateTime(i.scheduled_start) : "Time to be confirmed"}</p>
              {i.meeting_link && <p className="mt-1 text-sm"><a className="text-brand-700 underline" href={i.meeting_link} target="_blank" rel="noreferrer noopener">Join the meeting</a></p>}
              {i.location && <p className="mt-1 text-sm text-slate-700">Location: {i.location}</p>}
              {i.instructions && <p className="mt-1 whitespace-pre-wrap text-sm text-slate-600">{i.instructions}</p>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
