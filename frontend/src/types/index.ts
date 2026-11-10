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
  };
  registrations_by_day?: { date: string; applicants: number; employees: number }[];
  recent_applicants?: RecentPerson[];
  recent_employee_requests?: RecentPerson[];
  permissions?: string[];
  member_since?: string;
}
