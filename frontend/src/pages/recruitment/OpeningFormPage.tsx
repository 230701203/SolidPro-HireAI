import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Button, Card, ErrorState, Field, PageHeader, Select, Spinner, Textarea, TextInput } from "@/components/ui";
import TagInput from "@/components/TagInput";
import { useToast } from "@/components/Toast";
import { EMPLOYMENT_LABELS, WORK_MODE_LABELS } from "@/utils/labels";
import type { Assignee, Category, EmploymentType, Opening, WorkMode } from "@/types";

const schema = z.object({
  title: z.string().trim().min(3, "Enter a job title (at least 3 characters)").max(200),
  category_id: z.number("Choose a category").int().positive("Choose a category"),
  employment_type: z.enum(["full_time", "part_time", "contract", "internship"]),
  work_mode: z.enum(["onsite", "remote", "hybrid"]),
  location: z.string().max(150),
  vacancies: z.number("Enter the number of vacancies").int().min(1, "At least 1").max(1000),
  deadline: z.string(),
  required_experience: z.string().max(100),
  description: z.string().trim().min(10, "Describe the role (at least 10 characters)").max(20000),
  responsibilities: z.string().max(20000),
  required_qualifications: z.string().max(5000),
  preferred_qualifications: z.string().max(5000),
  required_skills: z.array(z.string()),
  preferred_skills: z.array(z.string()),
  intern_college: z.string(),
  intern_degree: z.string(),
  intern_department: z.string(),
  intern_graduation_year: z.string().regex(/^(\d{4})?$/, "Enter a 4-digit year"),
  intern_duration: z.string(),
  intern_availability: z.string(),
  intern_stipend: z.string(),
  assigned_employee_ids: z.array(z.number()),
});
type Form = z.infer<typeof schema>;

const blank = (s: string) => (s.trim() === "" ? null : s.trim());

const EMPTY: Form = {
  title: "", category_id: NaN, employment_type: "full_time", work_mode: "onsite", location: "", vacancies: 1, deadline: "", required_experience: "",
  description: "", responsibilities: "", required_qualifications: "", preferred_qualifications: "", required_skills: [], preferred_skills: [],
  intern_college: "", intern_degree: "", intern_department: "", intern_graduation_year: "", intern_duration: "", intern_availability: "", intern_stipend: "", assigned_employee_ids: [],
};

function toForm(o: Opening): Form {
  return {
    title: o.title, category_id: o.category_id, employment_type: o.employment_type, work_mode: o.work_mode, location: o.location ?? "", vacancies: o.vacancies,
    deadline: o.deadline ?? "", required_experience: o.required_experience ?? "", description: o.description, responsibilities: o.responsibilities ?? "",
    required_qualifications: o.required_qualifications ?? "", preferred_qualifications: o.preferred_qualifications ?? "", required_skills: o.required_skills, preferred_skills: o.preferred_skills,
    intern_college: o.intern_college ?? "", intern_degree: o.intern_degree ?? "", intern_department: o.intern_department ?? "",
    intern_graduation_year: o.intern_graduation_year ? String(o.intern_graduation_year) : "", intern_duration: o.intern_duration ?? "",
    intern_availability: o.intern_availability ?? "", intern_stipend: o.intern_stipend ?? "", assigned_employee_ids: o.assignees.map((a) => a.id),
  };
}

export default function OpeningFormPage() {
  const { id } = useParams();
  const editing = !!id;
  const navigate = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [serverError, setServerError] = useState<string | null>(null);

  const { data: cats } = useQuery({ queryKey: ["categories", "all"], queryFn: async () => (await api.get<Category[]>("/job-categories", { params: { include_inactive: true } })).data });
  const { data: people } = useQuery({ queryKey: ["assignable"], queryFn: async () => (await api.get<Assignee[]>("/job-openings/assignable-employees")).data });
  const existing = useQuery({ queryKey: ["opening", id], enabled: editing, queryFn: async () => (await api.get<Opening>(`/job-openings/${id}`)).data });

  const { register, handleSubmit, control, watch, reset, setError, formState: { errors, isSubmitting } } = useForm<Form>({ resolver: zodResolver(schema), defaultValues: EMPTY });
  useEffect(() => { if (existing.data) reset(toForm(existing.data)); }, [existing.data, reset]);

  const categoryId = watch("category_id");
  const employment = watch("employment_type");
  const isIntern = !!cats?.find((c) => c.id === categoryId)?.is_internship || employment === "internship";
  const activeCats = cats?.filter((c) => c.is_active || c.id === existing.data?.category_id);

  const onSubmit = async (v: Form) => {
    setServerError(null);
    const body = {
      ...v,
      location: blank(v.location), deadline: blank(v.deadline), required_experience: blank(v.required_experience), responsibilities: blank(v.responsibilities),
      required_qualifications: blank(v.required_qualifications), preferred_qualifications: blank(v.preferred_qualifications),
      intern_college: blank(v.intern_college), intern_degree: blank(v.intern_degree), intern_department: blank(v.intern_department),
      intern_graduation_year: v.intern_graduation_year ? Number(v.intern_graduation_year) : null, intern_duration: blank(v.intern_duration),
      intern_availability: blank(v.intern_availability), intern_stipend: blank(v.intern_stipend),
    };
    try {
      const { data } = editing ? await api.patch<Opening>(`/job-openings/${id}`, body) : await api.post<Opening>("/job-openings", body);
      void qc.invalidateQueries({ queryKey: ["openings"] });
      void qc.invalidateQueries({ queryKey: ["opening", String(data.id)] });
      toast.success(editing ? "Opening updated." : "Opening created as a draft. Publish it when it is ready.");
      navigate(`/openings/${data.id}`);
    } catch (e) {
      Object.entries(fieldErrors(e)).forEach(([k, m]) => setError(k as keyof Form, { message: m }));
      setServerError(errorMessage(e));
    }
  };

  if (editing && existing.isLoading) return <Spinner />;
  if (editing && existing.error) return <Card><ErrorState message={errorMessage(existing.error)} /></Card>;

  return (
    <>
      <PageHeader title={editing ? "Edit opening" : "New job opening"} description="Openings stay hidden from applicants until you publish them." />
      <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-6">
        {serverError && <Alert kind="error">{serverError}</Alert>}

        <Card className="space-y-4 p-5">
          <h2 className="font-semibold text-slate-900">Basics</h2>
          <Field label="Job title" htmlFor="title" error={errors.title?.message}><TextInput id="title" invalid={!!errors.title} {...register("title")} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Recruitment category" htmlFor="category_id" error={errors.category_id?.message}>
              <Select id="category_id" aria-invalid={!!errors.category_id} {...register("category_id", { setValueAs: (v) => (v === "" ? NaN : Number(v)) })}>
                <option value="">Select…</option>
                {activeCats?.map((c) => <option key={c.id} value={c.id}>{c.name}{c.is_active ? "" : " (inactive)"}</option>)}
              </Select>
            </Field>
            <Field label="Employment type" htmlFor="employment_type"><Select id="employment_type" {...register("employment_type")}>{(Object.keys(EMPLOYMENT_LABELS) as EmploymentType[]).map((k) => <option key={k} value={k}>{EMPLOYMENT_LABELS[k]}</option>)}</Select></Field>
            <Field label="Work mode" htmlFor="work_mode"><Select id="work_mode" {...register("work_mode")}>{(Object.keys(WORK_MODE_LABELS) as WorkMode[]).map((k) => <option key={k} value={k}>{WORK_MODE_LABELS[k]}</option>)}</Select></Field>
            <Field label="Location" htmlFor="location" error={errors.location?.message}><TextInput id="location" placeholder="e.g. Chennai" {...register("location")} /></Field>
            <Field label="Vacancies" htmlFor="vacancies" error={errors.vacancies?.message}><TextInput id="vacancies" type="number" min={1} {...register("vacancies", { valueAsNumber: true })} /></Field>
            <Field label="Application deadline" htmlFor="deadline" error={errors.deadline?.message}><TextInput id="deadline" type="date" {...register("deadline")} /></Field>
            <Field label="Required experience" htmlFor="required_experience" error={errors.required_experience?.message}><TextInput id="required_experience" placeholder="e.g. 2-4 years" {...register("required_experience")} /></Field>
          </div>
        </Card>

        <Card className="space-y-4 p-5">
          <h2 className="font-semibold text-slate-900">Description and requirements</h2>
          <Field label="Job description" htmlFor="description" error={errors.description?.message}><Textarea id="description" rows={5} invalid={!!errors.description} {...register("description")} /></Field>
          <Field label="Responsibilities" htmlFor="responsibilities"><Textarea id="responsibilities" rows={4} {...register("responsibilities")} /></Field>
          <Field label="Required technical skills" htmlFor="required_skills" error={errors.required_skills?.message} hint="Type a skill and press Enter. At least one is needed to publish.">
            <Controller control={control} name="required_skills" render={({ field }) => <TagInput id="required_skills" value={field.value} onChange={field.onChange} placeholder="e.g. Python, FastAPI" />} />
          </Field>
          <Field label="Preferred skills" htmlFor="preferred_skills">
            <Controller control={control} name="preferred_skills" render={({ field }) => <TagInput id="preferred_skills" value={field.value} onChange={field.onChange} placeholder="e.g. Docker" />} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Required qualifications" htmlFor="required_qualifications"><Textarea id="required_qualifications" rows={3} {...register("required_qualifications")} /></Field>
            <Field label="Preferred qualifications" htmlFor="preferred_qualifications"><Textarea id="preferred_qualifications" rows={3} {...register("preferred_qualifications")} /></Field>
          </div>
        </Card>

        {isIntern && (
          <Card className="space-y-4 p-5">
            <h2 className="font-semibold text-slate-900">Internship details</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="College" htmlFor="intern_college"><TextInput id="intern_college" {...register("intern_college")} /></Field>
              <Field label="Degree" htmlFor="intern_degree"><TextInput id="intern_degree" {...register("intern_degree")} /></Field>
              <Field label="Department" htmlFor="intern_department"><TextInput id="intern_department" {...register("intern_department")} /></Field>
              <Field label="Graduation year" htmlFor="intern_graduation_year" error={errors.intern_graduation_year?.message}><TextInput id="intern_graduation_year" inputMode="numeric" maxLength={4} {...register("intern_graduation_year")} /></Field>
              <Field label="Duration" htmlFor="intern_duration"><TextInput id="intern_duration" placeholder="e.g. 6 months" {...register("intern_duration")} /></Field>
              <Field label="Availability" htmlFor="intern_availability"><TextInput id="intern_availability" placeholder="e.g. Immediate" {...register("intern_availability")} /></Field>
              <Field label="Stipend (if applicable)" htmlFor="intern_stipend"><TextInput id="intern_stipend" {...register("intern_stipend")} /></Field>
            </div>
          </Card>
        )}

        <Card className="p-5">
          <h2 className="font-semibold text-slate-900">Assigned recruiters</h2>
          <p className="mb-3 mt-1 text-sm text-slate-500">Assigned employees can review this opening's applicants (if they hold the permission). You always keep access to openings you create.</p>
          <Controller
            control={control}
            name="assigned_employee_ids"
            render={({ field }) => (
              <div className="grid gap-2 sm:grid-cols-2">
                {people?.length === 0 && <p className="text-sm text-slate-500">No active employees yet.</p>}
                {people?.map((p) => (
                  <label key={p.id} className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">
                    <input type="checkbox" className="size-4 rounded border-slate-300" checked={field.value.includes(p.id)} onChange={() => field.onChange(field.value.includes(p.id) ? field.value.filter((x) => x !== p.id) : [...field.value, p.id])} />
                    <span><span className="block font-medium text-slate-900">{p.full_name}</span><span className="block text-xs text-slate-500">{p.email}</span></span>
                  </label>
                ))}
              </div>
            )}
          />
          {errors.assigned_employee_ids && <p role="alert" className="mt-2 text-xs text-red-600">{errors.assigned_employee_ids.message}</p>}
        </Card>

        <div className="flex justify-end gap-3">
          <Link to={editing ? `/openings/${id}` : "/openings"} className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Cancel</Link>
          <Button type="submit" loading={isSubmitting}>{editing ? "Save changes" : "Create draft"}</Button>
        </div>
      </form>
    </>
  );
}
