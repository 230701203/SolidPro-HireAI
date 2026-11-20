export type Role = "admin" | "employee" | "applicant";

export type AccountStatus =
  | "pending_email_verification"
  | "pending_approval"
  | "active"
  | "rejected"
  | "suspended"
  | "deactivated";

export interface User {
  id: number;
  email: string;
  full_name: string;
  mobile: string | null;
  role: Role;
  status: AccountStatus;
  must_change_password: boolean;
  email_verified_at: string | null;
  last_login_at: string | null;
  created_at: string;
  permissions: string[];
  department: string | null;
  designation: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface Permission {
  code: string;
  description: string;
  category: string;
}

export interface Employee {
  id: number;
  email: string;
  full_name: string;
  mobile: string | null;
  status: AccountStatus;
  created_at: string;
  email_verified_at: string | null;
  last_login_at: string | null;
  department: string | null;
  designation: string | null;
  permissions: string[];
}

export interface ApprovalHistory {
  decision: "approved" | "rejected";
  reason: string | null;
  decided_by_name: string | null;
  decided_at: string;
  permissions_granted: string[] | null;
}

export interface EmployeeDetail extends Employee {
  approvals: ApprovalHistory[];
}

export interface UserListItem {
  id: number;
  email: string;
  full_name: string;
  mobile: string | null;
  role: Role;
  status: AccountStatus;
  created_at: string;
  email_verified_at: string | null;
  last_login_at: string | null;
}

export interface AppNotification {
  id: number;
  type: string;
  title: string;
  message: string;
  link: string | null;
  is_read: boolean;
  created_at: string;
}

export interface AuditLogEntry {
  id: number;
  created_at: string;
  actor_id: number | null;
  actor_name: string | null;
  actor_email: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
}

export interface EmailDomain {
  id: number;
  domain: string;
  is_active: boolean;
  created_at: string;
}

export type EmailStatus = "queued" | "sent" | "failed" | "dev_logged";

export interface EmailLogEntry {
  id: number;
  to_email: string;
  subject: string;
  template: string;
  status: EmailStatus;
  attempts: number;
  error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface RecentPerson {
  id: number;
  full_name: string;
  email: string;
  created_at: string;
}

export interface DashboardSummary {
  role: Role;
  unread_notifications: number;
  cards?: {
    total_applicants: number;
    total_employees: number;
    pending_employee_approvals: number;
    suspended_accounts: number;
    total_openings: number;
    active_openings: number;
    total_applications: number;
    pending_application_reviews: number;
  };
  stats?: Record<string, number>;
  profile_completion?: number;
  profile_missing?: string[];
  registrations_by_day?: { date: string; applicants: number; employees: number }[];
  recent_applicants?: RecentPerson[];
  recent_employee_requests?: RecentPerson[];
  permissions?: string[];
  member_since?: string;
}

/* ------------------------------------------------------------------ Phase 2 */

export type EmploymentType = "full_time" | "part_time" | "contract" | "internship";
export type WorkMode = "onsite" | "remote" | "hybrid";
export type OpeningStatus = "draft" | "published" | "closed";
export type ApplicationStatus = "submitted" | "under_review" | "info_requested" | "approved" | "shortlisted" | "selected" | "rejected" | "withdrawn";
export type SkillKind = "technical" | "soft" | "tool" | "certification";
export type ExperienceKind = "job" | "internship" | "project";

export interface Category {
  id: number;
  name: string;
  description: string | null;
  is_internship: boolean;
  is_active: boolean;
  openings_count: number;
}

export interface Assignee {
  id: number;
  full_name: string;
  email: string;
}

export interface OpeningListItem {
  id: number;
  title: string;
  category_id: number;
  category_name: string;
  status: OpeningStatus;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  location: string | null;
  vacancies: number;
  deadline: string | null;
  is_open: boolean;
  applications_count: number;
  pending_count: number;
  assignees: Assignee[];
  created_at: string;
}

export interface OpeningFields {
  title: string;
  category_id: number;
  description: string;
  responsibilities: string | null;
  required_skills: string[];
  preferred_skills: string[];
  required_qualifications: string | null;
  preferred_qualifications: string | null;
  required_experience: string | null;
  employment_type: EmploymentType;
  work_mode: WorkMode;
  location: string | null;
  vacancies: number;
  deadline: string | null;
  intern_college: string | null;
  intern_degree: string | null;
  intern_department: string | null;
  intern_graduation_year: number | null;
  intern_duration: string | null;
  intern_availability: string | null;
  intern_stipend: string | null;
}

export interface Opening extends OpeningFields {
  id: number;
  status: OpeningStatus;
  category_name: string;
  category_is_internship: boolean;
  is_open: boolean;
  published_at: string | null;
  closed_at: string | null;
  created_at: string;
  created_by_name: string | null;
  applications_count: number;
  assignees: Assignee[];
}

export interface PublicJob extends Omit<OpeningFields, "category_id"> {
  id: number;
  category_name: string;
  published_at: string | null;
  is_internship: boolean;
  applied: boolean;
  application_id: number | null;
}

export interface Education {
  id?: number;
  degree: string;
  institution: string;
  department: string | null;
  graduation_year: number | null;
  grade: string | null;
}

export interface Experience {
  id?: number;
  kind: ExperienceKind;
  organization: string | null;
  title: string;
  start_date: string | null;
  end_date: string | null;
  description: string | null;
}

export interface Skill {
  id?: number;
  name: string;
  kind: SkillKind;
}

export interface Resume {
  id: number;
  version: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
  is_current: boolean;
}

export interface Profile {
  candidate_id: number;
  user_id: number;
  full_name: string;
  email: string;
  mobile: string | null;
  date_of_birth: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  linkedin_url: string | null;
  portfolio_url: string | null;
  github_url: string | null;
  highest_qualification: string | null;
  total_experience_years: number | null;
  education: Education[];
  experience: Experience[];
  skills: Skill[];
  resumes: Resume[];
  completion: number;
  missing: string[];
}

export interface ApplicantListItem {
  candidate_id: number;
  user_id: number;
  full_name: string;
  email: string;
  mobile: string | null;
  city: string | null;
  highest_qualification: string | null;
  applications_count: number;
  created_at: string;
}

export interface ApplicationListItem {
  id: number;
  status: ApplicationStatus;
  opening_id: number;
  opening_title: string;
  category_name: string;
  candidate_id: number;
  candidate_name: string;
  candidate_email: string;
  submitted_at: string;
  updated_at: string;
}

export interface HistoryItem {
  id: number;
  from_status: ApplicationStatus | null;
  to_status: ApplicationStatus;
  comment: string | null;
  actor_name: string | null;
  actor_role: string | null;
  visible_to_applicant: boolean;
  created_at: string;
}

export interface ApplicationDetail extends ApplicationListItem {
  cover_note: string | null;
  resume: Resume;
  decision_reason: string | null;
  decided_at: string | null;
  decided_by_name: string | null;
  history: HistoryItem[];
  can_review: boolean;
  candidate: Profile | null;
}

/* ------------------------------------------------------------------ Phase 3 */

export interface AnalysisResult {
  match_score: number;
  confidence: "low" | "medium" | "high";
  summary: string;
  matched_required_skills: string[];
  missing_required_skills: string[];
  matched_preferred_skills: string[];
  experience_assessment: string;
  education_assessment: string;
  strengths: string[];
  gaps: string[];
  clarifications_to_verify: string[];
  suggested_interview_topics: string[];
}

export interface AnalysisReport {
  id: number;
  application_id: number;
  resume_id: number;
  resume_version: number;
  status: "completed" | "failed";
  provider: string;
  model: string;
  prompt_version: string;
  is_mock: boolean;
  ai_score: number | null;
  effective_score: number | null;
  report: AnalysisResult | null;
  error: string | null;
  requested_by_name: string | null;
  created_at: string;
  override_score: number | null;
  override_note: string | null;
  overridden_by_name: string | null;
  overridden_at: string | null;
}

export interface AnalysisOverview {
  ai: { provider: string; model: string; is_mock: boolean; configured: boolean };
  notice: string;
  can_run: boolean;
  latest: AnalysisReport | null;
  history: AnalysisReport[];
}

/* ------------------------------------------------------------------ Phase 4 */

export type SectionKind = "mcq" | "aptitude" | "repeat_sentence";
export type QuestionStatus = "pending" | "approved" | "rejected";
export type Difficulty = "easy" | "medium" | "hard";
export type AptitudeTopic = "numerical" | "logical" | "analytical" | "verbal" | "data_interpretation" | "pattern";

export interface AQuestion {
  id: number; section: SectionKind; position: number; status: QuestionStatus; source: "ai" | "template" | "bank" | "manual";
  text: string; options: string[] | null; correct_index: number | null; explanation: string | null; difficulty: Difficulty;
  topic: string | null; skill: string | null; q_type: string | null; marks: number; edited: boolean; is_placeholder: boolean;
  reviewed_by_name: string | null; reviewed_at: string | null; reject_reason: string | null;
}
export interface ASection { id: number; kind: SectionKind; title: string; total_marks: number; questions: AQuestion[] }
export interface AVersion {
  id: number; version: number; total_marks: number; duration_minutes: number; content_hash: string;
  approved_by_name: string | null; approved_at: string; published_at: string | null; published_by_name: string | null;
}
export interface AApproval {
  id: number; version: number; reviewer_name: string | null; decision: string; note: string | null; question_ids: number[];
  changes: { first_version: boolean; added: number[]; removed: number[]; edited: number[] }; created_at: string;
}
export interface AssessmentDetail {
  id: number; application_id: number; candidate_name: string; opening_title: string; title: string; status: "draft" | "approved";
  difficulty: Difficulty; duration_minutes: number; config: Record<string, unknown>;
  ai: { provider: string; model: string; is_mock: boolean; prompt_version: string };
  created_by_name: string | null; created_at: string; updated_at: string; sections: ASection[]; total_marks: number;
  counts: { total: number; approved: number; pending: number; rejected: number }; blockers: string[]; has_unapproved_changes: boolean;
  latest_version: number | null; published_version: number | null; versions: AVersion[]; approvals: AApproval[]; generation_notes: string[];
  can_edit: boolean; can_generate: boolean; notice: string;
}
export interface AssessmentListItem {
  id: number; application_id: number; candidate_name: string; opening_title: string; title: string; status: "draft" | "approved";
  is_mock: boolean; total_marks: number; question_count: number; pending_count: number; latest_version: number | null;
  published_version: number | null; created_at: string;
}
export interface VersionDetail {
  version: number; content_hash: string; integrity_ok: boolean; total_marks: number; duration_minutes: number;
  approved_by_name: string | null; approved_at: string; published_at: string | null;
  snapshot: { sections: { kind: SectionKind; title: string; total_marks: number; questions: unknown[] }[] };
}
export interface Bank {
  id: number; name: string; description: string | null; category_id: number | null; category_name: string | null;
  is_active: boolean; question_count: number; active_question_count: number;
}
export interface BankQuestion {
  id: number; bank_id: number; topic: AptitudeTopic; text: string; options: string[]; correct_index: number; explanation: string | null;
  difficulty: Difficulty; marks: number; is_active: boolean; source: string; verified_by_name: string | null; updated_at: string;
}

export interface ImportRowIssue { row: number; message: string; skipped: boolean }
export interface ImportResult { dry_run: boolean; total_rows: number; valid: number; imported: number; duplicates: number; failed: number; issues: ImportRowIssue[] }

/* ---- Phase 5: scheduling and online tests ---- */
export type ScheduleStatus = "invited" | "accepted" | "in_progress" | "completed" | "expired" | "cancelled";
export type AttemptStatus = "in_progress" | "submitted";
export interface RescheduleItem {
  id: number; reason: string; preferred_start: string | null; status: string; comment: string | null;
  new_window_start: string | null; new_window_end: string | null; created_at: string; decided_at: string | null;
}
export interface ScheduleListItem {
  id: number; application_id: number; candidate_name: string; opening_title: string; assessment_title: string; status: ScheduleStatus;
  window_start: string; window_end: string; duration_minutes: number; pending_reschedule: boolean; attempt_status: AttemptStatus | null;
}
export interface ScheduleDetail extends ScheduleListItem {
  assessment_id: number; version: number; is_mock: boolean; instructions: string | null; link_expires_at: string; accepted_at: string | null;
  cancelled_at: string | null; cancel_reason: string | null; candidate_email: string; reschedules: RescheduleItem[];
  events: { id: number; kind: string; client_reported: boolean; details: Record<string, unknown> | null; created_at: string }[];
  attempt: { id: number; status: AttemptStatus; started_at: string; deadline_at: string; submitted_at: string | null; submit_reason: string | null; answered: number; total_questions: number; recordings: number } | null;
  can_edit: boolean; can_manage: boolean; evaluation_id: number | null; invite_link: string | null;
}
export interface RecordingItem { id: number; question_id: number; attempt_no: number; size_bytes: number; duration_ms: number | null; mime: string; created_at: string }
export interface Invitation {
  id: number; application_id: number; opening_title: string; assessment_title: string; status: ScheduleStatus; window_start: string; window_end: string;
  duration_minutes: number; instructions: string | null; link_expires_at: string; sections: { kind: string; title: string; questions: number }[];
  has_repeat_sentence: boolean; rs_max_replays: number | null; rs_max_attempts: number | null; rs_record_seconds: number | null;
  can_accept: boolean; can_start: boolean; start_blocked_reason: string | null; can_request_reschedule: boolean; attempt_id: number | null;
  reschedules: RescheduleItem[]; server_now: string;
}
export interface TakeQuestion {
  id: number; section: string; position: number; text: string | null; options: { id: number; text: string }[] | null; marks: number;
  selected: number | null; marked: boolean; plays_used: number; plays_allowed: number | null; recordings_used: number; recordings_allowed: number | null;
}
export interface TakeAttempt {
  id: number; status: AttemptStatus; assessment_title: string; started_at: string; deadline_at: string; server_now: string; submitted_at: string | null;
  session_id: string | null; rs_record_seconds: number | null; sections: { kind: string; title: string; questions: TakeQuestion[] }[];
}

/* ---- Phase 6: evaluation, results, interviews ---- */
export interface SpeechView {
  expected: string; recognized: string; confidence: number | null; accuracy: number | null; completeness: number | null; missing: string[];
  substituted: { expected: string; heard: string }[]; near_matches: { expected: string; heard: string }[]; extra: string[]; order_differs: boolean;
  provider: string | null; is_mock: boolean; error: string | null;
}
export interface EvalItem {
  id: number; question_id: number; section: string; position: number; text: string; options: string[] | null; selected_index: number | null; selected_text: string | null;
  correct_index: number | null; correct_text: string | null; is_correct: boolean | null; unanswered: boolean; max_marks: number; auto_marks: number | null; final_marks: number | null;
  overridden: boolean; needs_review: boolean; review_note: string | null; stt_status: string; speech: SpeechView | null; recordings: { id: number; attempt_no: number; is_final: boolean }[];
}
export interface EvalListItem {
  id: number; application_id: number; schedule_id: number; candidate_name: string; opening_title: string; test_date: string | null; status: "draft" | "final";
  total_marks: number; total_obtained: number; percentage: number | null; unresolved: number; released: boolean; application_status: ApplicationStatus;
}
export interface EvalDetail extends EvalListItem {
  candidate_email: string; assessment_title: string; assessment_is_mock: boolean; duration_minutes: number; time_taken_seconds: number | null; summary: string | null;
  sections: { kind: string; title: string; obtained: number; total: number; correct: number; incorrect: number; unanswered: number; unresolved: number }[];
  groups: { kind: string; title: string; items: EvalItem[] }[];
  overrides: { id: number; item_id: number; question_position: number; section: string; original_marks: number | null; revised_marks: number; reason: string; changed_by: string | null; changed_at: string }[];
  comments: { id: number; author: string | null; body: string; created_at: string }[];
  blockers: string[]; can_edit: boolean; speech_provider: string | null; speech_is_mock: boolean; applicant_feedback: string | null; finalized_at: string | null; released_at: string | null;
}
export interface MyResult {
  id: number; application_id: number; opening_title: string; assessment_title: string; test_date: string | null; released_at: string; total_marks: number; total_obtained: number;
  percentage: number | null; sections: { kind: string; title: string; obtained: number; total: number }[]; time_taken_seconds: number | null; feedback: string | null;
}
export type InterviewStatus = "pending" | "scheduled" | "completed" | "rescheduled" | "cancelled";
export interface InterviewFeedback {
  technical_feedback: string | null; communication_feedback: string | null; strengths: string | null; improvements: string | null; recommendation: string; submitted_by?: string | null; updated_at?: string;
}
export interface InterviewItem {
  id: number; application_id: number; candidate_name: string; opening_title: string; interviewer: { id: number; full_name: string } | null; interview_type: string; mode: string;
  status: InterviewStatus; scheduled_start: string | null; duration_minutes: number; meeting_link: string | null; location: string | null; instructions: string | null;
  cancel_reason: string | null; feedback: InterviewFeedback | null; can_manage: boolean; can_give_feedback: boolean;
}
export interface MyInterview {
  id: number; opening_title: string; interview_type: string; mode: string; status: InterviewStatus; scheduled_start: string | null; duration_minutes: number;
  meeting_link: string | null; location: string | null; instructions: string | null;
}

// ---- Phase 7: bulk screening and analytics
export interface BulkProgress { queued: number; processing: number; done: number; failed: number; total: number; finished: number; complete: boolean }
export interface BulkBatch {
  id: number; name: string; opening_id: number; opening_title: string; created_by_name: string | null; created_at: string;
  ai_provider: string | null; ai_is_mock: boolean | null; progress: BulkProgress;
}
export interface BulkItem {
  id: number; filename: string; size_bytes: number; status: "queued" | "processing" | "done" | "failed"; error: string | null; attempts: number;
  candidate_name: string | null; email: string | null; phone: string | null; skills: string[]; experience_years: number | null; match_score: number | null;
  duplicate_kind: "existing_applicant" | "duplicate_in_batch" | "duplicate_file" | null; duplicate_of_item_id: number | null;
  existing_applicant: boolean; existing_application_id: number | null;
  review_status: "unreviewed" | "interesting" | "not_suitable"; review_note: string | null; warnings: string[];
}
export interface BulkItemDetail extends BulkItem { education: string[]; analysis: Record<string, unknown> | null }
export interface BulkCreated { batch: BulkBatch; rejected: { filename: string; reason: string }[] }

export interface Analytics {
  totals: { applications: number; pending: number; approved: number; rejected: number; withdrawn: number; shortlisted: number; selected: number; openings_in_scope: number; decided: number };
  rates: { approval_rate: number | null; rejection_rate: number | null; completion_rate: number | null; attendance_rate: number | null; shortlisting_rate: number | null; selection_rate: number | null };
  denominators: Record<string, number>;
  status_distribution: { status: string; count: number }[];
  funnel: { stage: string; count: number }[];
  per_opening: AnalyticsRow[];
  per_category: AnalyticsRow[];
  applications_by_month: { month: string; count: number }[];
  scores: { evaluated_candidates: number; average_percentage: number | null; distribution: { range: string; count: number }[]; performance_trend: { month: string; average: number | null; count: number }[] };
  match_scores: { analysed: number; average: number | null; trend: { month: string; average: number | null; count: number }[]; top_matched_skills: { skill: string; count: number }[]; top_missing_skills: { skill: string; count: number }[] };
  stage_durations: { stage: string; avg_days: number | null; sample: number }[];
  notes: string[];
  generated_at: string;
}
export interface AnalyticsRow { id: number; name: string; applications: number; approved: number; rejected: number; shortlisted: number; selected: number }
export interface CompareRow {
  application_id: number; candidate_name: string; opening_title: string; status: string; experience_years: number | null; match_score: number | null; match_is_mock: boolean | null;
  matched_required_skills: string[]; missing_required_skills: string[]; evaluation_percentage: number | null; sections: { section: string; obtained: number; total: number }[];
}
