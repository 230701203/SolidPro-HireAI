import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, errorMessage } from "@/services/api";
import {
  Alert, Badge, Button, Card, EmptyState, ErrorState, Field, Modal, PageHeader, Pagination, Select, Spinner, StatusBadge,
  TableWrap, Textarea, TextInput, td, th, useDebounced,
} from "@/components/ui";
import { useToast } from "@/components/Toast";
import { formatDate, formatDateTime } from "@/utils/format";
import { PERMISSION_LABELS } from "@/utils/permissions";
import type { AccountStatus, Employee, EmployeeDetail, Page, Permission } from "@/types";

type Dialog = { kind: "approve" | "reject" | "permissions" | "details"; employee: Employee } | null;

function PermissionPicker({ all, value, onChange }: { all: Permission[]; value: string[]; onChange: (v: string[]) => void }) {
  const groups = all.reduce<Record<string, Permission[]>>((acc, p) => ((acc[p.category] ??= []).push(p), acc), {});
  const toggle = (code: string) => onChange(value.includes(code) ? value.filter((c) => c !== code) : [...value, code]);
  return (
    <div className="space-y-4">
      {Object.entries(groups).map(([cat, perms]) => (
        <fieldset key={cat}>
          <legend className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{cat}</legend>
          <div className="space-y-1.5">
            {perms.map((p) => (
              <label key={p.code} className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-slate-200 px-3 py-2 hover:bg-slate-50">
                <input type="checkbox" className="mt-0.5 size-4 rounded border-slate-300" checked={value.includes(p.code)} onChange={() => toggle(p.code)} />
                <span>
                  <span className="block text-sm font-medium text-slate-900">{PERMISSION_LABELS[p.code] ?? p.code}</span>
                  <span className="block text-xs text-slate-500">{p.description}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </div>
  );
}

function EmployeeDialog({ dialog, onClose }: { dialog: NonNullable<Dialog>; onClose: () => void }) {
  const { kind, employee } = dialog;
  const qc = useQueryClient();
  const toast = useToast();
  const [perms, setPerms] = useState<string[]>(employee.permissions);
  const [department, setDepartment] = useState(employee.department ?? "");
  const [designation, setDesignation] = useState(employee.designation ?? "");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: all } = useQuery({
    queryKey: ["permissions"],
    queryFn: async () => (await api.get<Permission[]>("/permissions")).data,
    enabled: kind === "approve" || kind === "permissions",
  });
  const { data: detail, isLoading: detailLoading } = useQuery({
    queryKey: ["employee", employee.id],
    queryFn: async () => (await api.get<EmployeeDetail>(`/employees/${employee.id}`)).data,
    enabled: kind === "details",
  });

  const done = (msg: string) => {
    toast.success(msg);
    void qc.invalidateQueries({ queryKey: ["employees"] });
    void qc.invalidateQueries({ queryKey: ["dashboard"] });
    onClose();
  };

  const m = useMutation({
    mutationFn: async () => {
      if (kind === "approve") return api.post(`/employees/${employee.id}/approve`, { permission_codes: perms, department: department || null, designation: designation || null });
      if (kind === "reject") return api.post(`/employees/${employee.id}/reject`, { reason });
      return api.put(`/employees/${employee.id}/permissions`, { permission_codes: perms });
    },
    onSuccess: () => done(kind === "approve" ? `${employee.full_name} approved. They were notified by email.` : kind === "reject" ? `${employee.full_name} rejected.` : "Permissions updated."),
    onError: (e) => setError(errorMessage(e)),
  });

  const titles = { approve: `Approve ${employee.full_name}`, reject: `Reject ${employee.full_name}`, permissions: `Permissions for ${employee.full_name}`, details: employee.full_name };

  const footer =
    kind === "details" ? <Button variant="secondary" onClick={onClose}>Close</Button> : (
      <>
        <Button variant="secondary" onClick={onClose} disabled={m.isPending}>Cancel</Button>
        <Button
          variant={kind === "reject" ? "danger" : "primary"}
          loading={m.isPending}
          disabled={kind === "reject" && reason.trim().length < 3}
          onClick={() => { setError(null); m.mutate(); }}
        >
          {kind === "approve" ? "Approve employee" : kind === "reject" ? "Reject registration" : "Save permissions"}
        </Button>
      </>
    );

  return (
    <Modal open onClose={onClose} title={titles[kind]} footer={footer} wide={kind !== "reject"}>
      {error && <div className="mb-4"><Alert kind="error">{error}</Alert></div>}
      {kind === "approve" && (
        <div className="space-y-5">
          <p className="text-sm text-slate-600">{employee.email} verified their company email. Choose what this employee may do. Nothing is granted by default.</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Department (optional)" htmlFor="dept"><TextInput id="dept" value={department} onChange={(e) => setDepartment(e.target.value)} maxLength={100} /></Field>
            <Field label="Designation (optional)" htmlFor="desig"><TextInput id="desig" value={designation} onChange={(e) => setDesignation(e.target.value)} maxLength={100} /></Field>
          </div>
          {all ? <PermissionPicker all={all} value={perms} onChange={setPerms} /> : <Spinner />}
        </div>
      )}
      {kind === "reject" && (
        <Field label="Reason (sent to the employee)" htmlFor="reason" hint="At least 3 characters.">
          <Textarea id="reason" rows={4} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} />
        </Field>
      )}
      {kind === "permissions" && (all ? <PermissionPicker all={all} value={perms} onChange={setPerms} /> : <Spinner />)}
      {kind === "details" && (detailLoading || !detail ? <Spinner /> : (
        <div className="space-y-5 text-sm">
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2">
            <dt className="text-slate-500">Email</dt><dd>{detail.email}</dd>
            <dt className="text-slate-500">Mobile</dt><dd>{detail.mobile ?? "—"}</dd>
            <dt className="text-slate-500">Status</dt><dd><StatusBadge status={detail.status} /></dd>
            <dt className="text-slate-500">Department</dt><dd>{detail.department ?? "—"}</dd>
            <dt className="text-slate-500">Designation</dt><dd>{detail.designation ?? "—"}</dd>
            <dt className="text-slate-500">Registered</dt><dd>{formatDateTime(detail.created_at)}</dd>
            <dt className="text-slate-500">Email verified</dt><dd>{formatDateTime(detail.email_verified_at)}</dd>
            <dt className="text-slate-500">Last sign-in</dt><dd>{formatDateTime(detail.last_login_at)}</dd>
            <dt className="text-slate-500">Permissions</dt>
            <dd className="flex flex-wrap gap-1.5">{detail.permissions.length ? detail.permissions.map((p) => <Badge key={p} tone="blue">{PERMISSION_LABELS[p] ?? p}</Badge>) : "None"}</dd>
          </dl>
          <div>
            <h3 className="mb-2 font-semibold text-slate-900">Approval history</h3>
            {detail.approvals.length === 0 ? <p className="text-slate-500">No decisions yet.</p> : (
              <ul className="space-y-2">
                {detail.approvals.map((a, i) => (
                  <li key={i} className="rounded-lg border border-slate-200 px-3 py-2">
                    <div className="flex items-center justify-between"><Badge tone={a.decision === "approved" ? "green" : "red"}>{a.decision === "approved" ? "Approved" : "Rejected"}</Badge><span className="text-xs text-slate-500">{formatDateTime(a.decided_at)} by {a.decided_by_name ?? "unknown"}</span></div>
                    {a.reason && <p className="mt-1 text-slate-600">Reason: {a.reason}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}
    </Modal>
  );
}

export default function EmployeesPage() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") ?? "") as AccountStatus | "";
  const [search, setSearch] = useState("");
  const debounced = useDebounced(search);
  const [page, setPage] = useState(1);
  const [dialog, setDialog] = useState<Dialog>(null);
  useEffect(() => setPage(1), [debounced, status]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["employees", status, debounced, page],
    queryFn: async () => (await api.get<Page<Employee>>("/employees", { params: { status: status || undefined, search: debounced || undefined, page, page_size: 15 } })).data,
  });

  return (
    <>
      <PageHeader title="Employee management" description="Approve SolidPro employee registrations and control what each employee can do." />
      <Card>
        <div className="flex flex-wrap gap-3 border-b border-slate-200 p-4">
          <div className="relative min-w-56 flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <TextInput aria-label="Search employees" placeholder="Search name or email" className="pl-9" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
          <Select aria-label="Filter by status" className="w-full sm:w-56" value={status} onChange={(e) => { const p = new URLSearchParams(params); e.target.value ? p.set("status", e.target.value) : p.delete("status"); setParams(p); }}>
            <option value="">All statuses</option>
            <option value="pending_approval">Pending approval</option>
            <option value="active">Active</option>
            <option value="rejected">Rejected</option>
            <option value="suspended">Suspended</option>
            <option value="pending_email_verification">Awaiting email verification</option>
          </Select>
        </div>
        {isLoading ? <Spinner /> : error || !data ? <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /> : data.items.length === 0 ? (
          <EmptyState title="No employees found" description={status || debounced ? "Try changing your filters." : "Employees appear here after they register with a company email."} />
        ) : (
          <>
            <TableWrap>
              <thead><tr><th className={th}>Employee</th><th className={th}>Status</th><th className={th}>Permissions</th><th className={th}>Registered</th><th className={`${th} text-right`}>Actions</th></tr></thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id} className="hover:bg-slate-50/60">
                    <td className={td}><button className="text-left" onClick={() => setDialog({ kind: "details", employee: e })}><span className="block font-medium text-slate-900 hover:underline">{e.full_name}</span><span className="block text-xs text-slate-500">{e.email}</span></button></td>
                    <td className={td}><StatusBadge status={e.status} /></td>
                    <td className={td}>{e.status === "active" ? <span className="text-slate-600">{e.permissions.length} granted</span> : <span className="text-slate-400">—</span>}</td>
                    <td className={td}>{formatDate(e.created_at)}</td>
                    <td className={`${td} text-right`}>
                      <div className="flex justify-end gap-2">
                        {(e.status === "pending_approval" || e.status === "rejected") && <Button size="sm" onClick={() => setDialog({ kind: "approve", employee: e })}>Approve</Button>}
                        {e.status === "pending_approval" && <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "reject", employee: e })}>Reject</Button>}
                        {e.status === "active" && <Button size="sm" variant="secondary" onClick={() => setDialog({ kind: "permissions", employee: e })}>Permissions</Button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </TableWrap>
            <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} />
          </>
        )}
      </Card>
      {dialog && <EmployeeDialog key={`${dialog.kind}-${dialog.employee.id}`} dialog={dialog} onClose={() => setDialog(null)} />}
    </>
  );
}
