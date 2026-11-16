import { Badge, Card } from "@/components/ui";
import ResumeLinks from "@/components/ResumeLinks";
import { formatDate } from "@/utils/format";
import { EXPERIENCE_KIND_LABELS, SKILL_KIND_LABELS } from "@/utils/labels";
import type { Profile, SkillKind } from "@/types";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words text-slate-900">{children || "—"}</dd>
    </>
  );
}

function Link({ href }: { href: string | null }) {
  return href ? <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-brand-700 hover:underline">{href}</a> : <>—</>;
}

/** Read-only candidate profile for recruiters. Resume versions are listed newest first. */
export default function ProfileView({ p }: { p: Profile }) {
  const kinds = Object.keys(SKILL_KIND_LABELS) as SkillKind[];
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Personal details</h2>
        <dl className="grid grid-cols-[9rem_1fr] gap-x-4 gap-y-2 text-sm">
          <Row label="Name">{p.full_name}</Row>
          <Row label="Email">{p.email}</Row>
          <Row label="Mobile">{p.mobile}</Row>
          <Row label="Location">{[p.city, p.state, p.country].filter(Boolean).join(", ")}</Row>
          <Row label="LinkedIn"><Link href={p.linkedin_url} /></Row>
          <Row label="GitHub"><Link href={p.github_url} /></Row>
          <Row label="Portfolio"><Link href={p.portfolio_url} /></Row>
          <Row label="Highest qualification">{p.highest_qualification}</Row>
          <Row label="Experience">{p.total_experience_years != null ? `${p.total_experience_years} years` : null}</Row>
        </dl>
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Education</h2>
        {p.education.length === 0 ? <p className="text-sm text-slate-500">None provided.</p> : (
          <ul className="space-y-3">
            {p.education.map((e) => (
              <li key={e.id} className="text-sm">
                <p className="font-medium text-slate-900">{e.degree}{e.department ? `, ${e.department}` : ""}</p>
                <p className="text-slate-600">{e.institution}{e.graduation_year ? ` · ${e.graduation_year}` : ""}{e.grade ? ` · ${e.grade}` : ""}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Experience and projects</h2>
        {p.experience.length === 0 ? <p className="text-sm text-slate-500">None provided.</p> : (
          <ul className="space-y-3">
            {p.experience.map((x) => (
              <li key={x.id} className="text-sm">
                <p className="font-medium text-slate-900">{x.title} <Badge>{EXPERIENCE_KIND_LABELS[x.kind]}</Badge></p>
                <p className="text-slate-600">{[x.organization, x.start_date ? `${formatDate(x.start_date)} – ${x.end_date ? formatDate(x.end_date) : "present"}` : null].filter(Boolean).join(" · ")}</p>
                {x.description && <p className="mt-1 whitespace-pre-wrap text-slate-700">{x.description}</p>}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Skills</h2>
        {p.skills.length === 0 ? <p className="text-sm text-slate-500">None provided.</p> : (
          <div className="space-y-3">
            {kinds.map((k) => {
              const list = p.skills.filter((s) => s.kind === k);
              return list.length ? (
                <div key={k}>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{SKILL_KIND_LABELS[k]}</p>
                  <div className="flex flex-wrap gap-1.5">{list.map((s) => <Badge key={s.id} tone="blue">{s.name}</Badge>)}</div>
                </div>
              ) : null;
            })}
          </div>
        )}
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Resume versions</h2>
        {p.resumes.length === 0 ? <p className="text-sm text-slate-500">No resume uploaded.</p> : <div className="space-y-2">{p.resumes.map((r) => <ResumeLinks key={r.id} resume={r} />)}</div>}
      </Card>
    </div>
  );
}
