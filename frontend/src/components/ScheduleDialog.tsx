import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Button, Field, Modal, Textarea, TextInput } from "@/components/ui";
import { localToIso } from "@/components/ScheduleBadge";
import { useToast } from "@/components/Toast";
import type { ScheduleDetail } from "@/types";

function pad(n: number) { return String(n).padStart(2, "0"); }
function localValue(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }

/** Create (or, with `existing`, edit) a schedule. The invitation link is shown once after creation. */
export default function ScheduleDialog({ applicationId, existing, durationMinutes, onClose, onDone }: {
  applicationId: number; existing?: ScheduleDetail; durationMinutes: number; onClose: () => void; onDone?: (s: ScheduleDetail) => void;
}) {
  const qc = useQueryClient();
  const toast = useToast();
  const soon = new Date(Date.now() + 60 * 60 * 1000);
  const [start, setStart] = useState(localValue(existing ? new Date(existing.window_start) : soon));
  const [end, setEnd] = useState(localValue(existing ? new Date(existing.window_end) : new Date(soon.getTime() + 24 * 60 * 60 * 1000)));
  const [instructions, setInstructions] = useState(existing?.instructions ?? "");
  const [err, setErr] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [link, setLink] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: async () => {
      const body = { window_start: localToIso(start), window_end: localToIso(end), instructions: instructions || null };
      return (existing ? await api.patch<ScheduleDetail>(`/schedules/${existing.id}`, body) : await api.post<ScheduleDetail>("/schedules", { ...body, application_id: applicationId })).data;
    },
    onSuccess: (s) => {
      void qc.invalidateQueries({ queryKey: ["schedules"] });
      void qc.invalidateQueries({ queryKey: ["schedule"] });
      onDone?.(s);
      if (s.invite_link) setLink(s.invite_link);
      else onClose();
      toast.success(existing ? "Schedule updated." : "Invitation sent.");
    },
    onError: (e) => { setErr(errorMessage(e)); setFields(fieldErrors(e)); },
  });

  if (link) {
    return (
      <Modal open onClose={onClose} title="Invitation sent" footer={<Button onClick={onClose}>Done</Button>}>
        <p className="text-sm text-slate-700">The applicant was emailed and notified in the app. This link is shown only now, copy it if you need to share it another way. It only works for the invited applicant when logged in.</p>
        <input readOnly aria-label="Invitation link" className="mt-3 w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-xs" value={link} onFocus={(e) => e.currentTarget.select()} />
      </Modal>
    );
  }
  return (
    <Modal open onClose={onClose} title={existing ? "Edit schedule" : "Schedule online assessment"}
      footer={<><Button variant="secondary" onClick={onClose} disabled={save.isPending}>Cancel</Button><Button loading={save.isPending} onClick={() => { setErr(null); setFields({}); save.mutate(); }}>{existing ? "Save and re-invite" : "Send invitation"}</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <p className="text-sm text-slate-600">The applicant can start any time inside this window and then has {existing?.duration_minutes ?? durationMinutes} minutes. Times use your device's timezone.</p>
        <Field label="Window opens" htmlFor="sch-start" error={fields.window_start}><TextInput id="sch-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
        <Field label="Window closes" htmlFor="sch-end" error={fields.window_end}><TextInput id="sch-end" type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
        <Field label="Instructions for the applicant (optional)" htmlFor="sch-ins"><Textarea id="sch-ins" rows={3} maxLength={3000} value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}
