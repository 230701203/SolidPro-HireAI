import { useRef, useState } from "react";
import { Controller, useFieldArray, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, Upload } from "lucide-react";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Button, Card, ErrorState, Field, PageHeader, Select, Spinner, Textarea, TextInput } from "@/components/ui";
import TagInput from "@/components/TagInput";
import ResumeLinks from "@/components/ResumeLinks";
import { useToast } from "@/components/Toast";
import { EXPERIENCE_KIND_LABELS, SKILL_KIND_LABELS } from "@/utils/labels";
import type { ExperienceKind, Profile, Resume, SkillKind } from "@/types";

const url = z.string().refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Enter a full URL starting with http:// or https://");
const schema = z.object({
  date_of_birth: z.string(), address: z.string().max(500), city: z.string().max(100), state: z.string().max(100), country: z.string().max(100),
  linkedin_url: url, portfolio_url: url, github_url: url, highest_qualification: z.string().max(150),
  total_experience_years: z.string().refine((v) => v === "" || (!isNaN(Number(v)) && Number(v) >= 0 && Number(v) <= 60), "Enter a number between 0 and 60"),
  education: z.array(z.object({
    degree: z.string().trim().min(2, "Enter the degree"), institution: z.string().trim().min(2, "Enter the institution"),
    department: z.string(), graduation_year: z.string().regex(/^(\d{4})?$/, "4-digit year"), grade: z.string(),
  })),
  experience: z.array(z.object({
    kind: z.enum(["job", "internship", "project"]), organization: z.string(), title: z.string().trim().min(2, "Enter a title"),
    start_date: z.string(), end_date: z.string(), description: z.string().max(3000),
  })),
  skills_technical: z.array(z.string()), skills_soft: z.array(z.string()), skills_tool: z.array(z.string()), skills_certification: z.array(z.string()),
});
type Form = z.infer<typeof schema>;
const n = (s: string) => (s.trim() === "" ? null : s.trim());
const KINDS: SkillKind[] = ["technical", "soft", "tool", "certification"];

function toForm(p: Profile): Form {
  const by = (k: SkillKind) => p.skills.filter((s) => s.kind === k).map((s) => s.name);
  return {
    date_of_birth: p.date_of_birth ?? "", address: p.address ?? "", city: p.city ?? "", state: p.state ?? "", country: p.country ?? "",
    linkedin_url: p.linkedin_url ?? "", portfolio_url: p.portfolio_url ?? "", github_url: p.github_url ?? "", highest_qualification: p.highest_qualification ?? "",
    total_experience_years: p.total_experience_years != null ? String(p.total_experience_years) : "",
    education: p.education.map((e) => ({ degree: e.degree, institution: e.institution, department: e.department ?? "", graduation_year: e.graduation_year ? String(e.graduation_year) : "", grade: e.grade ?? "" })),
    experience: p.experience.map((x) => ({ kind: x.kind, organization: x.organization ?? "", title: x.title, start_date: x.start_date ?? "", end_date: x.end_date ?? "", description: x.description ?? "" })),
    skills_technical: by("technical"), skills_soft: by("soft"), skills_tool: by("tool"), skills_certification: by("certification"),
  };
}

const MAX_MB = 5;
const OK_EXT = [".pdf", ".docx"];

function ResumeUpload({ resumes }: { resumes: Resume[] }) {
  const qc = useQueryClient();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState<string | null>(null);
  const up = useMutation({
    mutationFn: async (f: File) => { const fd = new FormData(); fd.append("file", f); return (await api.post<Resume>("/applicants/resumes", fd)).data; },
    onSuccess: () => { toast.success("Resume uploaded."); void qc.invalidateQueries({ queryKey: ["my-profile"] }); },
    onError: (e) => setErr(errorMessage(e)),
  });
  const pick = (f?: File) => {
    setErr(null);
    if (!f) return;
    if (!OK_EXT.some((x) => f.name.toLowerCase().endsWith(x))) return setErr("Upload a PDF or DOCX file.");
    if (f.size > MAX_MB * 1024 * 1024) return setErr(`The file is larger than ${MAX_MB} MB.`);
    up.mutate(f);
  };
  return (
    <Card className="space-y-3 p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold text-slate-900">Resume</h2>
        <Button variant="secondary" size="sm" loading={up.isPending} onClick={() => input.current?.click()}><Upload className="size-4" /> Upload {resumes.length ? "new version" : "resume"}</Button>
        <input ref={input} type="file" aria-label="Resume file" accept=".pdf,.docx" className="hidden" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </div>
      <p className="text-xs text-slate-500">PDF or DOCX, up to {MAX_MB} MB. Scanned (image-only) PDFs are not supported yet. Older versions are kept, and applications keep the version you applied with.</p>
      {err && <Alert kind="error">{err}</Alert>}
      {resumes.length === 0 ? <p className="text-sm text-slate-500">No resume uploaded yet. You need one to apply.</p> : <div className="space-y-2">{resumes.map((r) => <ResumeLinks key={r.id} resume={r} />)}</div>}
    </Card>
  );
}

export default function ProfileEditPage() {
  const qc = useQueryClient();
  const toast = useToast();
  const [serverError, setServerError] = useState<string | null>(null);
  const { data: p, isLoading, error, refetch } = useQuery({ queryKey: ["my-profile"], queryFn: async () => (await api.get<Profile>("/applicants/profile")).data });
  const form = useForm<Form>({ resolver: zodResolver(schema), defaultValues: p ? toForm(p) : undefined, values: p ? toForm(p) : undefined });
  const { register, control, handleSubmit, setError, formState: { errors, isSubmitting } } = form;
  const edu = useFieldArray({ control, name: "education" });
  const exp = useFieldArray({ control, name: "experience" });

  if (isLoading) return <Spinner />;
  if (error || !p) return <Card><ErrorState message={errorMessage(error)} onRetry={() => void refetch()} /></Card>;

  const onSubmit = async (v: Form) => {
    setServerError(null);
    const skills = KINDS.flatMap((k) => v[`skills_${k}` as const].map((name) => ({ name, kind: k })));
    try {
      await api.put("/applicants/profile", {
        date_of_birth: n(v.date_of_birth), address: n(v.address), city: n(v.city), state: n(v.state), country: n(v.country),
        linkedin_url: n(v.linkedin_url), portfolio_url: n(v.portfolio_url), github_url: n(v.github_url), highest_qualification: n(v.highest_qualification),
        total_experience_years: v.total_experience_years === "" ? null : Number(v.total_experience_years),
        education: v.education.map((e) => ({ degree: e.degree, institution: e.institution, department: n(e.department), graduation_year: e.graduation_year ? Number(e.graduation_year) : null, grade: n(e.grade) })),
        experience: v.experience.map((x) => ({ kind: x.kind, organization: n(x.organization), title: x.title, start_date: n(x.start_date), end_date: n(x.end_date), description: n(x.description) })),
        skills,
      });
      toast.success("Profile saved.");
      void qc.invalidateQueries({ queryKey: ["my-profile"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    } catch (e) {
      Object.entries(fieldErrors(e)).forEach(([k, m]) => { try { setError(k as keyof Form, { message: m }); } catch { /* nested server path */ } });
      setServerError(errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader title="My profile" description="Keep this up to date. Recruiters see it when you apply." />
      <Card className="mb-6 p-5">
        <div className="flex items-center justify-between text-sm"><span className="font-medium text-slate-900">Profile completion</span><span className="tabular-nums">{p.completion}%</span></div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100" role="progressbar" aria-valuenow={p.completion} aria-valuemin={0} aria-valuemax={100} aria-label="Profile completion"><div className="h-full bg-brand-600" style={{ width: `${p.completion}%` }} /></div>
        {p.missing.length > 0 && <p className="mt-2 text-xs text-slate-500">Still to add: {p.missing.join(", ")}</p>}
      </Card>
      <div className="space-y-6">
        <ResumeUpload resumes={p.resumes} />
        <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
          {serverError && <Alert kind="error">{serverError}</Alert>}
          <Card className="space-y-4 p-5">
            <h2 className="font-semibold text-slate-900">Personal details</h2>
            <p className="text-xs text-slate-500">Name, email and mobile are managed under Account &amp; password.</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Date of birth" htmlFor="date_of_birth" error={errors.date_of_birth?.message}><TextInput id="date_of_birth" type="date" {...register("date_of_birth")} /></Field>
              <Field label="Highest qualification" htmlFor="highest_qualification"><TextInput id="highest_qualification" placeholder="e.g. B.E. Mechanical" {...register("highest_qualification")} /></Field>
              <Field label="City" htmlFor="city"><TextInput id="city" {...register("city")} /></Field>
              <Field label="State" htmlFor="state"><TextInput id="state" {...register("state")} /></Field>
              <Field label="Country" htmlFor="country"><TextInput id="country" {...register("country")} /></Field>
              <Field label="Total experience (years)" htmlFor="total_experience_years" error={errors.total_experience_years?.message}><TextInput id="total_experience_years" inputMode="decimal" {...register("total_experience_years")} /></Field>
            </div>
            <Field label="Address" htmlFor="address"><Textarea id="address" rows={2} {...register("address")} /></Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="LinkedIn" htmlFor="linkedin_url" error={errors.linkedin_url?.message}><TextInput id="linkedin_url" placeholder="https://" {...register("linkedin_url")} /></Field>
              <Field label="Portfolio" htmlFor="portfolio_url" error={errors.portfolio_url?.message}><TextInput id="portfolio_url" placeholder="https://" {...register("portfolio_url")} /></Field>
              <Field label="GitHub" htmlFor="github_url" error={errors.github_url?.message}><TextInput id="github_url" placeholder="https://" {...register("github_url")} /></Field>
            </div>
          </Card>

          <Card className="space-y-4 p-5">
            <div className="flex items-center justify-between"><h2 className="font-semibold text-slate-900">Education</h2><Button type="button" variant="secondary" size="sm" onClick={() => edu.append({ degree: "", institution: "", department: "", graduation_year: "", grade: "" })}><Plus className="size-4" /> Add education</Button></div>
            {edu.fields.length === 0 && <p className="text-sm text-slate-500">Add at least one education entry to apply.</p>}
            {edu.fields.map((f, i) => (
              <div key={f.id} className="space-y-3 rounded-lg border border-slate-200 p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Degree" htmlFor={`edu-degree-${i}`} error={errors.education?.[i]?.degree?.message}><TextInput id={`edu-degree-${i}`} {...register(`education.${i}.degree`)} /></Field>
                  <Field label="Institution" htmlFor={`edu-inst-${i}`} error={errors.education?.[i]?.institution?.message}><TextInput id={`edu-inst-${i}`} {...register(`education.${i}.institution`)} /></Field>
                  <Field label="Department" htmlFor={`edu-dept-${i}`}><TextInput id={`edu-dept-${i}`} {...register(`education.${i}.department`)} /></Field>
                  <Field label="Graduation year" htmlFor={`edu-year-${i}`} error={errors.education?.[i]?.graduation_year?.message}><TextInput id={`edu-year-${i}`} inputMode="numeric" maxLength={4} {...register(`education.${i}.graduation_year`)} /></Field>
                  <Field label="Grade / CGPA" htmlFor={`edu-grade-${i}`}><TextInput id={`edu-grade-${i}`} {...register(`education.${i}.grade`)} /></Field>
                </div>
                <Button type="button" variant="ghost" size="sm" onClick={() => edu.remove(i)}><Trash2 className="size-4" /> Remove</Button>
              </div>
            ))}
          </Card>

          <Card className="space-y-4 p-5">
            <div className="flex items-center justify-between"><h2 className="font-semibold text-slate-900">Experience, internships and projects</h2><Button type="button" variant="secondary" size="sm" onClick={() => exp.append({ kind: "job", organization: "", title: "", start_date: "", end_date: "", description: "" })}><Plus className="size-4" /> Add entry</Button></div>
            {exp.fields.length === 0 && <p className="text-sm text-slate-500">Optional, but it helps recruiters.</p>}
            {exp.fields.map((f, i) => (
              <div key={f.id} className="space-y-3 rounded-lg border border-slate-200 p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label="Type" htmlFor={`exp-kind-${i}`}><Select id={`exp-kind-${i}`} {...register(`experience.${i}.kind`)}>{(Object.keys(EXPERIENCE_KIND_LABELS) as ExperienceKind[]).map((k) => <option key={k} value={k}>{EXPERIENCE_KIND_LABELS[k]}</option>)}</Select></Field>
                  <Field label="Title / role" htmlFor={`exp-title-${i}`} error={errors.experience?.[i]?.title?.message}><TextInput id={`exp-title-${i}`} {...register(`experience.${i}.title`)} /></Field>
                  <Field label="Organization" htmlFor={`exp-org-${i}`}><TextInput id={`exp-org-${i}`} {...register(`experience.${i}.organization`)} /></Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Start" htmlFor={`exp-start-${i}`}><TextInput id={`exp-start-${i}`} type="date" {...register(`experience.${i}.start_date`)} /></Field>
                    <Field label="End" htmlFor={`exp-end-${i}`}><TextInput id={`exp-end-${i}`} type="date" {...register(`experience.${i}.end_date`)} /></Field>
                  </div>
                </div>
                <Field label="Description" htmlFor={`exp-desc-${i}`}><Textarea id={`exp-desc-${i}`} rows={3} {...register(`experience.${i}.description`)} /></Field>
                <Button type="button" variant="ghost" size="sm" onClick={() => exp.remove(i)}><Trash2 className="size-4" /> Remove</Button>
              </div>
            ))}
          </Card>

          <Card className="space-y-4 p-5">
            <h2 className="font-semibold text-slate-900">Skills</h2>
            {KINDS.map((k) => (
              <Field key={k} label={SKILL_KIND_LABELS[k]} htmlFor={`skills_${k}`} hint="Type and press Enter.">
                <Controller control={control} name={`skills_${k}` as const} render={({ field }) => <TagInput id={`skills_${k}`} value={field.value ?? []} onChange={field.onChange} />} />
              </Field>
            ))}
          </Card>
          <div className="flex justify-end"><Button type="submit" loading={isSubmitting}>Save profile</Button></div>
        </form>
      </div>
    </>
  );
}
