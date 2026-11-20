import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Bell, Briefcase, CheckCircle2, ClipboardList, FileText, ShieldCheck, UserCheck, UserCog, Users } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { api, errorMessage } from "@/services/api";
import { Alert, Badge, Card, EmptyState, ErrorState, PageHeader, Spinner } from "@/components/ui";
import { timeAgo } from "@/utils/format";
import { PERMISSION_LABELS } from "@/utils/permissions";
import type { DashboardSummary, RecentPerson } from "@/types";

function StatCard({ label, value, icon: Icon, to, tone = "blue" }: { label: string; value: number; icon: typeof Users; to?: string; tone?: "blue" | "amber" | "slate" | "red" }) {
  const tones = { blue: "bg-brand-50 text-brand-700", amber: "bg-amber-50 text-amber-700", slate: "bg-slate-100 text-slate-600", red: "bg-red-50 text-red-700" };
  const body = (
    <Card className="flex items-center gap-4 p-5 transition-shadow hover:shadow-md">
      <span className={`flex size-11 items-center justify-center rounded-lg ${tones[tone]}`}><Icon className="size-5" /></span>
      <div>
        <p className="text-2xl font-semibold tabular-nums text-slate-900">{value}</p>
        <p className="text-sm text-slate-500">{label}</p>
      </div>
    </Card>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

function RecentList({ title, people, empty, to }: { title: string; people: RecentPerson[]; empty: string; to: string }) {
  return (
    <Card>
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
        <h2 className="font-semibold text-slate-900">{title}</h2>
        <Link to={to} className="text-sm font-medium text-brand-700 hover:underline">View all</Link>
      </div>
      {people.length === 0 ? (
        <p className="px-5 py-8 text-center text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {people.map((p) => (
            <li key={p.id} className="flex items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-900">{p.full_name}</p>
                <p className="truncate text-xs text-slate-500">{p.email}</p>
              </div>
              <span className="shrink-0 text-xs text-slate-500">{timeAgo(p.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AdminDashboard({ d }: { d: DashboardSummary }) {
  const c = d.cards!;
  const series = (d.registrations_by_day ?? []).map((r) => ({ ...r, label: r.date.slice(5) }));
  return (
    <>
      {c.pending_employee_approvals > 0 && (
        <div className="mb-6">
          <Alert kind="warning">
            {c.pending_employee_approvals} employee registration{c.pending_employee_approvals > 1 ? "s are" : " is"} waiting for your approval.{" "}
            <Link to="/admin/employees" className="font-medium underline">Review now</Link>
          </Alert>
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total applicants" value={c.total_applicants} icon={Users} to="/admin/users?role=applicant" />
        <StatCard label="Active employees" value={c.total_employees} icon={UserCheck} to="/admin/employees?status=active" />
        <StatCard label="Pending approvals" value={c.pending_employee_approvals} icon={UserCog} tone="amber" to="/admin/employees?status=pending_approval" />
        <StatCard label="Suspended / deactivated" value={c.suspended_accounts} icon={ShieldCheck} tone="red" to="/admin/users?status=suspended" />
      </div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total openings" value={c.total_openings} icon={Briefcase} to="/openings" tone="slate" />
        <StatCard label="Published openings" value={c.active_openings} icon={Briefcase} to="/openings?status=published" />
        <StatCard label="Applications" value={c.total_applications} icon={FileText} to="/applications" tone="slate" />
        <StatCard label="Awaiting review" value={c.pending_application_reviews} icon={ClipboardList} to="/applications?status=submitted" tone="amber" />
      </div>
      <Card className="mt-6 p-5">
        <h2 className="font-semibold text-slate-900">New registrations, last 30 days</h2>
        <div className="mt-4 h-64" role="img" aria-label="Bar chart of new applicant and employee registrations per day">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={series} margin={{ left: -20 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} interval={4} />
              <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="applicants" name="Applicants" stackId="a" fill="#2563eb" />
              <Bar dataKey="employees" name="Employees" stackId="a" fill="#f59e0b" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <RecentList title="Newly registered applicants" people={d.recent_applicants ?? []} empty="No applicants yet." to="/admin/users?role=applicant" />
        <RecentList title="Employee requests awaiting approval" people={d.recent_employee_requests ?? []} empty="Nothing is waiting for approval." to="/admin/employees?status=pending_approval" />
      </div>
      <p className="mt-6 text-xs text-slate-500">AI resume analysis and assessment metrics will appear here in later phases.</p>
    </>
  );
}



export default function DashboardPage() {
  const { user } = useAuth();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["dashboard", user?.id],
    queryFn: async () => (await api.get<DashboardSummary>("/dashboard/summary")).data,
  });

  if (!user) return null;
  const titles = { admin: "Admin dashboard", employee: "Employee dashboard", applicant: "My dashboard" };

  return (
    <>
      <PageHeader title={titles[user.role]} description={`Welcome back, ${user.full_name}.`} />

      {isLoading ? (
        <Spinner />
      ) : error || !data ? (
        <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>
      ) : user.role === "admin" ? (
        <AdminDashboard d={data} />
      ) : user.role === "employee" ? (
        <Card className="p-6">
          <h2 className="font-semibold text-slate-900">Your access</h2>
          {data.permissions && data.permissions.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {data.permissions.map((p) => <Badge key={p} tone="blue">{PERMISSION_LABELS[p] ?? p}</Badge>)}
            </div>
          ) : (
            <EmptyState title="No permissions assigned yet" description="An administrator controls which recruitment functions you can use. Contact them to request access." />
          )}
          {data.stats && (
            <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Assigned openings" value={data.stats.assigned_openings ?? 0} icon={Briefcase} to="/openings" tone="slate" />
              <StatCard label="Applicants" value={data.stats.assigned_applicants ?? 0} icon={Users} to="/applicants" tone="slate" />
              <StatCard label="Pending reviews" value={data.stats.pending_reviews ?? 0} icon={ClipboardList} to="/applications" tone="amber" />
              <StatCard label="Approved" value={data.stats.approved ?? 0} icon={CheckCircle2} />
              <StatCard label="Shortlisted" value={data.stats.shortlisted ?? 0} icon={CheckCircle2} to="/results" />
            </div>
          )}
          <p className="mt-4 text-xs text-slate-500">You only see openings you were assigned to or created.</p>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card className="p-6">
            <div className="flex items-center justify-between text-sm"><h2 className="font-semibold text-slate-900">Profile completion</h2><span className="tabular-nums">{data.profile_completion ?? 0}%</span></div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={data.profile_completion ?? 0} aria-valuemin={0} aria-valuemax={100} aria-label="Profile completion"><div className="h-full bg-brand-600" style={{ width: `${data.profile_completion ?? 0}%` }} /></div>
            {(data.profile_missing?.length ?? 0) > 0 && <p className="mt-2 text-sm text-slate-600">Still to add: {data.profile_missing!.join(", ")}. <Link to="/applicant/profile" className="font-medium text-brand-700 hover:underline">Complete profile</Link></p>}
          </Card>
          {data.stats && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Applications" value={data.stats.total_applications ?? 0} icon={FileText} to="/my-applications" tone="slate" />
              <StatCard label="In progress" value={data.stats.under_review ?? 0} icon={ClipboardList} tone="amber" />
              <StatCard label="Approved" value={data.stats.approved ?? 0} icon={CheckCircle2} />
              <StatCard label="Shortlisted / selected" value={data.stats.shortlisted ?? 0} icon={CheckCircle2} />
              <StatCard label="Not selected" value={data.stats.rejected ?? 0} icon={FileText} tone="slate" />
            </div>
          )}
          <Card className="p-6">
            <Link to="/jobs" className="inline-flex items-center gap-2 text-sm font-medium text-brand-700 hover:underline"><Briefcase className="size-4" /> Browse open positions</Link>
            <Link to="/notifications" className="mt-3 flex items-center gap-2 text-sm font-medium text-brand-700 hover:underline">
              <Bell className="size-4" /> {data.unread_notifications} unread notification{data.unread_notifications === 1 ? "" : "s"}
            </Link>
          </Card>
        </div>
      )}
    </>
  );
}
