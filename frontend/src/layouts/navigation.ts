import {
  Bell,
  Briefcase,
  CalendarClock,
  Award,
  BarChart3,
  Upload,
  Video,
  ClipboardCheck,
  PenLine,
  Library,
  FileText,
  FolderTree,
  LayoutDashboard,
  Mail,
  ScrollText,
  Search,
  Settings,
  UserCircle,
  UserCog,
  Users,
  ContactRound,
  type LucideIcon,
} from "lucide-react";
import type { Role } from "@/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Shown only when the user holds this permission (admins always do). UX only; the API enforces it. */
  permission?: string;
  /** Shown when the user holds at least one of these permissions. */
  anyPermission?: string[];
  /** Sidebar section this item sits under. Items without a group are shown on their own. */
  group?: string;
}

/** Icon for each collapsible sidebar section. */
export const GROUP_ICONS: Record<string, LucideIcon> = {
  Hiring: Briefcase,
  "Tests & Interviews": ClipboardCheck,
  Administration: Settings,
  "My Applications": FileText,
  "My Assessments": PenLine,
  Account: UserCircle,
};

/** Only pages that exist in the current phase are listed, so there are no dead links. */
export const NAV: Record<Role, NavItem[]> = {
  admin: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/categories", label: "Job Categories", icon: FolderTree, group: "Hiring" },
    { to: "/openings", label: "Job Openings", icon: Briefcase, group: "Hiring" },
    { to: "/applicants", label: "Applicants", icon: ContactRound, group: "Hiring" },
    { to: "/applications", label: "Applications", icon: FileText, group: "Hiring" },
    { to: "/bulk", label: "Bulk Screening", icon: Upload, group: "Hiring" },
    { to: "/analytics", label: "Analytics", icon: BarChart3, group: "Hiring" },
    { to: "/assessments", label: "Assessments", icon: ClipboardCheck, group: "Tests & Interviews" },
    { to: "/question-bank", label: "Question Bank", icon: Library, group: "Tests & Interviews" },
    { to: "/schedules", label: "Test Schedules", icon: CalendarClock, group: "Tests & Interviews" },
    { to: "/results", label: "Results", icon: Award, group: "Tests & Interviews" },
    { to: "/interviews", label: "Interviews", icon: Video, group: "Tests & Interviews" },
    { to: "/admin/employees", label: "Employee Management", icon: UserCog, group: "Administration" },
    { to: "/admin/users", label: "All Users", icon: Users, group: "Administration" },
    { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText, group: "Administration" },
    { to: "/admin/email-logs", label: "Email Delivery", icon: Mail, group: "Administration" },
    { to: "/admin/settings", label: "System Settings", icon: Settings, group: "Administration" },
    { to: "/notifications", label: "Notifications", icon: Bell },
  ],
  employee: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/openings", label: "My Assigned Openings", icon: Briefcase, group: "Hiring" },
    { to: "/applicants", label: "Applicants", icon: ContactRound, permission: "review_applications", group: "Hiring" },
    { to: "/applications", label: "Applications", icon: FileText, permission: "review_applications", group: "Hiring" },
    { to: "/categories", label: "Job Categories", icon: FolderTree, permission: "manage_categories", group: "Hiring" },
    { to: "/bulk", label: "Bulk Screening", icon: Upload, permission: "bulk_upload_resumes", group: "Hiring" },
    { to: "/analytics", label: "Analytics", icon: BarChart3, permission: "view_analytics", group: "Hiring" },
    { to: "/assessments", label: "Assessments", icon: ClipboardCheck, anyPermission: ["generate_assessments", "approve_assessments"], group: "Tests & Interviews" },
    { to: "/question-bank", label: "Question Bank", icon: Library, anyPermission: ["manage_question_bank", "generate_assessments", "approve_assessments"], group: "Tests & Interviews" },
    { to: "/schedules", label: "Test Schedules", icon: CalendarClock, permission: "schedule_tests", group: "Tests & Interviews" },
    { to: "/results", label: "Results", icon: Award, permission: "review_results", group: "Tests & Interviews" },
    { to: "/interviews", label: "Interviews", icon: Video, group: "Tests & Interviews" },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/profile", label: "My Profile", icon: UserCog },
  ],
  applicant: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/jobs", label: "Browse Jobs", icon: Search, group: "My Applications" },
    { to: "/my-applications", label: "My Applications", icon: FileText, group: "My Applications" },
    { to: "/my-tests", label: "My Tests", icon: PenLine, group: "My Assessments" },
    { to: "/my-results", label: "My Results", icon: Award, group: "My Assessments" },
    { to: "/my-interviews", label: "My Interviews", icon: Video, group: "My Assessments" },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/applicant/profile", label: "My Profile", icon: UserCircle, group: "Account" },
    { to: "/profile", label: "Account Settings", icon: Settings, group: "Account" },
  ],
};
