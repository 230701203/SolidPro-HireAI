import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Button, Field, Modal, Select, Textarea, TextInput } from "@/components/ui";
import { localToIso } from "@/components/ScheduleBadge";
import { useToast } from "@/components/Toast";
import type { InterviewItem } from "@/types";

function pad(n: number) { return String(n).padStart(2, "0"); }
function localValue(d: Date) { return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; }

/** Create (with applicationId) or edit (with `existing`) an interview. Changing the time notifies the applicant. */
export default function InterviewDialog({ applicationId, existing, onClose }: { applicationId?: number; existing?: InterviewItem; onClose: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [start, setStart] = useState(existing?.scheduled_start ? localValue(new Date(existing.scheduled_start)) : "");
  const [type, setType] = useState(existing?.interview_type ?? "technical");
  const [mode, setMode] = useState(existing?.mode ?? "online");
  const [duration, setDuration] = useState(String(existing?.duration_minutes ?? 45));
  const [link, setLink] = useState(existing?.meeting_link ?? "");
  const [location, setLocation] = useState(existing?.location ?? "");
  const [instructions, setInstructions] = useState(existing?.instructions ?? "");
  const [interviewer, setInterviewer] = useState(existing?.interviewer ? String(existing.interviewer.id) : "");
  const [err, setErr] = useState<string | null>(null);
  const [fields, setFields] = useState<Record<string, string>>({});

  const save = useMutation({
    mutationFn: async () => {
      const body = {
        interview_type: type, mode, duration_minutes: Number(duration), meeting_link: link || null, location: location || null, instructions: instructions || null,
        scheduled_start: start ? localToIso(start) : null, interviewer_id: interviewer ? Number(interviewer) : null,
      };
      return existing ? (await api.patch<InterviewItem>(`/interviews/${existing.id}`, body)).data : (await api.post<InterviewItem>("/interviews", { ...body, application_id: applicationId })).data;
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["interviews"] }); void qc.invalidateQueries({ queryKey: ["interview"] }); toast.success(existing ? "Interview updated." : "Interview created."); onClose(); },
    onError: (e) => { setErr(errorMessage(e)); setFields(fieldErrors(e)); },
  });

  return (
    <Modal open onClose={onClose} title={existing ? "Edit interview" : "Schedule interview"}
      footer={<><Button variant="secondary" onClick={onClose} disabled={save.isPending}>Cancel</Button><Button loading={save.isPending} onClick={() => { setErr(null); setFields({}); save.mutate(); }}>{existing ? "Save" : "Create"}</Button></>}>
      <div className="space-y-4">
        {err && <Alert kind="error">{err}</Alert>}
        <p className="text-sm text-slate-600">The applicant is emailed and notified when a time is set or changed. Leave the time empty to keep the interview pending. Times use your device's timezone.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Date and time" htmlFor="iv-start" error={fields.scheduled_start}><TextInput id="iv-start" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
          <Field label="Duration (minutes)" htmlFor="iv-dur" error={fields.duration_minutes}><TextInput id="iv-dur" type="number" min={10} max={480} value={duration} onChange={(e) => setDuration(e.target.value)} /></Field>
          <Field label="Type" htmlFor="iv-type"><Select id="iv-type" value={type} onChange={(e) => setType(e.target.value)}>{["technical", "hr", "managerial", "panel", "other"].map((t) => <option key={t} value={t}>{t}</option>)}</Select></Field>
          <Field label="Mode" htmlFor="iv-mode"><Select id="iv-mode" value={mode} onChange={(e) => setMode(e.target.value)}>{["online", "onsite", "phone"].map((t) => <option key={t} value={t}>{t}</option>)}</Select></Field>
        </div>
        <Field label="Interviewer (user id, optional)" htmlFor="iv-who" error={fields.interviewer_id}><TextInput id="iv-who" inputMode="numeric" value={interviewer} onChange={(e) => setInterviewer(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 12" /></Field>
        <Field label="Meeting link (https://…)" htmlFor="iv-link" error={fields.meeting_link}><TextInput id="iv-link" value={link} onChange={(e) => setLink(e.target.value)} /></Field>
        <Field label="Location (for on-site)" htmlFor="iv-loc"><TextInput id="iv-loc" value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
        <Field label="Instructions for the applicant" htmlFor="iv-ins"><Textarea id="iv-ins" rows={3} value={instructions} onChange={(e) => setInstructions(e.target.value)} /></Field>
      </div>
    </Modal>
  );
}
