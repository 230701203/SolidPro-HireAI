import type { ApplicationStatus, EmploymentType, ExperienceKind, OpeningStatus, SkillKind, WorkMode } from "@/types";

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  internship: "Internship",
};
export const WORK_MODE_LABELS: Record<WorkMode, string> = { onsite: "On-site", remote: "Remote", hybrid: "Hybrid" };
export const OPENING_STATUS_LABELS: Record<OpeningStatus, string> = { draft: "Draft", published: "Published", closed: "Closed" };
export const APPLICATION_STATUS_LABELS: Record<ApplicationStatus, string> = {
  submitted: "Submitted",
  under_review: "Under review",
  info_requested: "Information requested",
  approved: "Approved for assessment",
  shortlisted: "Shortlisted",
  selected: "Selected",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};
export const SKILL_KIND_LABELS: Record<SkillKind, string> = {
  technical: "Technical skills",
  soft: "Soft skills",
  tool: "Tools & technologies",
  certification: "Certifications",
};
export const EXPERIENCE_KIND_LABELS: Record<ExperienceKind, string> = { job: "Job", internship: "Internship", project: "Project" };

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
