import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import {
  Button, Card, ConfirmDialog, EmptyState, ErrorState, PageHeader, Pagination, RoleBadge, Select, Spinner, StatusBadge,
  TableWrap, TextInput, td, th, useDebounced,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { formatDate, formatDateTime } from "@/utils/format";
import type { Page, UserListItem } from "@/types";

type Action = { kind: "suspended" | "deactivated" | "active" | "reset" | "unlock"; user: UserListItem } | null;

const COPY: Record<NonNullable<Action>["kind"], { title: string; confirm: string; danger?: boolean; body: (n: string) => string }> = {
  suspended: { title: "Suspend account", confirm: "Suspend", danger: true, body: (n) => `${n} will be signed out immediately and cannot sign in until reactivated.` },
  deactivated: { title: "Deactivate account", confirm: "Deactivate", danger: true, body: (n) => `${n} will be signed out immediately and the account will be disabled.` },
  active: { title: "Reactivate account", confirm: "Reactivate", body: (n) => `${n} will be able to sign in again.` },
  reset: { title: "Send password reset", confirm: "Send reset link", body: (n) => `A password reset link will be emailed to ${n}. You will not see or set their password.` },
  unlock: { title: "Unlock account", confirm: "Unlock", body: (n) => `Clear the failed-login lock for ${n}.` },
};

export default function UsersPage() {
  const { user: me } = useAuth();
  const [params, setParams] = useSearchParams();
  const role = params.get("role") ?? "";
  const status = params.get("status") ?? "";
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search);
  const [page, setPage] = useState(1);
  const [action, setAction] = useState<Action>(null);
  const qc = useQueryClient();
  const toast = useToast();
  useEffect(() => setPage(1), [debounced, role, status]);

  const setParam = (k: string, v: string) => { const p = new URLSearchParams(params); v ? p.set(k, v) : p.delete(k); setParams(p); };

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["users", role, status, debounced, page],
    queryFn: async () => (await api.get<Page<UserListItem>>("/users", { params: { role: role || undefined, status: status || undefined, search: debounced || undefined, page, page_size: 15 } })).data,
  });

  const run = useMutation({
    mutationFn: async (a: NonNullable<Action>) => {
      if (a.kind === "reset") return (await api.post<{ message: string }>(`/users/${a.user.id}/password-reset`)).data.message;
      if (a.kind === "unlock") return (await api.post<{ message: string }>(`/users/${a.user.id}/unlock`)).data.message;
      await api.patch(`/users/${a.user.id}/status`, { status: a.kind });
      return `${a.user.full_name} is now ${a.kind}.`;
    },
    onSuccess: (msg) => { toast.success(msg); setAction(null); void qc.invalidateQueries({ queryKey: ["users"] }); void qc.invalidateQueries({ queryKey: ["dashboard"] }); },
    onError: (e) => { toast.error(errorMessage(e)); setAction(null); },
  });

  return (
    <>
      <PageHeader title="All users" description="Search accounts, change their status, and start password recovery." />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search users" placeholder="Search name, email or mobile" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by account type" className="w-full sm:w-44" value={role} onChange={(e) => setParam("role", e.target.value)}>
            <option value="">All account types</option><option value="admin">Admin</option><option value="employee">Employee</option><option value="applicant">Applicant</option>
          </Select>
          <Select aria-label="Filter by status" className="w-full sm:w-52" value={status} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">All statuses</option><option value="active">Active</option><option value="pending_approval">Pending approval</option><option value="pending_email_verification">Awaiting verification</option><option value="rejected">Rejected</option><option value="suspended">Suspended</option><option value="deactivated">Deactivated</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No users match" description="Try different search terms or filters." />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>User</th><th className={th}>Type</th><th className={th}>Status</th><th className={th}>Registered</th><th className={th}>Last sign-in</th><th className={`${th} text-right`}>Actions</th></tr></thead>
              <tbody>
                {data.items.map((u) => {
                  const settled = u.status === "active" || u.status === "suspended" || u.status === "deactivated";
                  const self = u.id === me?.id;
                  return (
                    <tr key={u.id} className="hover:bg-slate-50/60">
                      <td className={td}><span className="block font-medium text-slate-900">{u.full_name}</span><span className="block text-xs text-slate-500">{u.email}</span></td>
                      <td className={td}><RoleBadge role={u.role} /></td>
                      <td className={td}><StatusBadge status={u.status} /></td>
                      <td className={td}>{formatDate(u.created_at)}</td>
                      <td className={td}>{formatDateTime(u.last_login_at)}</td>
                      <td className={`${td} text-right`}>
                        <div className="flex flex-wrap justify-end gap-2">
                          {settled && !self && (u.status === "active" ? (
                            <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "suspended", user: u })}>Suspend</Button>
                          ) : (
                            <Button size="sm" variant="secondary" onClick={() => setAction({ kind: "active", user: u })}>Reactivate</Button>
                          ))}
                          {settled && !self && u.status === "active" && <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "deactivated", user: u })}>Deactivate</Button>}
                          {u.status !== "pending_email_verification" && u.status !== "rejected" && <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "reset", user: u })}>Reset password</Button>}
                          <Button size="sm" variant="ghost" onClick={() => setAction({ kind: "unlock", user: u })}>Unlock</Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </TableWrap>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
      {action && (
        <ConfirmDialog
          open
          title={COPY[action.kind].title}
          message={COPY[action.kind].body(action.kind === "reset" ? action.user.email : action.user.full_name)}
          confirmLabel={COPY[action.kind].confirm}
          danger={COPY[action.kind].danger}
          loading={run.isPending}
          onConfirm={() => run.mutate(action)}
          onCancel={() => setAction(null)}
        />
      )}
    </>
  );
}
