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
}

/** Only pages that exist in the current phase are listed, so there are no dead links. */
export const NAV: Record<Role, NavItem[]> = {
  admin: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/admin/employees", label: "Employee Management", icon: UserCog },
    { to: "/admin/users", label: "All Users", icon: Users },
    { to: "/applicants", label: "Applicants", icon: ContactRound },
    { to: "/categories", label: "Job Categories", icon: FolderTree },
    { to: "/openings", label: "Job Openings", icon: Briefcase },
    { to: "/applications", label: "Applications", icon: FileText },
    { to: "/assessments", label: "Assessments", icon: ClipboardCheck },
    { to: "/schedules", label: "Test Schedules", icon: CalendarClock },
    { to: "/results", label: "Results", icon: Award },
    { to: "/interviews", label: "Interviews", icon: Video },
    { to: "/bulk", label: "Bulk Screening", icon: Upload },
    { to: "/analytics", label: "Analytics", icon: BarChart3 },
    { to: "/question-bank", label: "Question Bank", icon: Library },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText },
    { to: "/admin/email-logs", label: "Email Delivery", icon: Mail },
    { to: "/admin/settings", label: "System Settings", icon: Settings },
  ],
  employee: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/openings", label: "My Assigned Openings", icon: Briefcase },
    { to: "/applicants", label: "Applicants", icon: ContactRound, permission: "review_applications" },
    { to: "/applications", label: "Applications", icon: FileText, permission: "review_applications" },
    { to: "/categories", label: "Job Categories", icon: FolderTree, permission: "manage_categories" },
    { to: "/assessments", label: "Assessments", icon: ClipboardCheck, anyPermission: ["generate_assessments", "approve_assessments"] },
    { to: "/schedules", label: "Test Schedules", icon: CalendarClock, permission: "schedule_tests" },
    { to: "/results", label: "Results", icon: Award, permission: "review_results" },
    { to: "/interviews", label: "Interviews", icon: Video },
    { to: "/bulk", label: "Bulk Screening", icon: Upload, permission: "bulk_upload_resumes" },
    { to: "/analytics", label: "Analytics", icon: BarChart3, permission: "view_analytics" },
    { to: "/question-bank", label: "Question Bank", icon: Library, anyPermission: ["manage_question_bank", "generate_assessments", "approve_assessments"] },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/profile", label: "My Profile", icon: UserCog },
  ],
  applicant: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/applicant/profile", label: "My Profile", icon: UserCircle },
    { to: "/jobs", label: "Browse Jobs", icon: Search },
    { to: "/my-applications", label: "My Applications", icon: FileText },
    { to: "/my-tests", label: "My Tests", icon: PenLine },
    { to: "/my-results", label: "My Results", icon: Award },
    { to: "/my-interviews", label: "My Interviews", icon: Video },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/profile", label: "Account Settings", icon: Settings },
  ],
};
