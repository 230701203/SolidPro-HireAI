import {
  Bell,
  ClipboardList,
  FileSearch,
  LayoutDashboard,
  Mail,
  ScrollText,
  Settings,
  ShieldCheck,
  UserCog,
  Users,
  type LucideIcon,
} from "lucide-react";
import type { Role } from "@/types";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

/**
 * Only pages that exist in the current phase are listed, so there are no dead links.
 * Later phases append their entries here (job openings, applications, assessments, ...).
 */
export const NAV: Record<Role, NavItem[]> = {
  admin: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/admin/employees", label: "Employee Management", icon: UserCog },
    { to: "/admin/users", label: "All Users", icon: Users },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/admin/audit-logs", label: "Audit Logs", icon: ScrollText },
    { to: "/admin/email-logs", label: "Email Delivery", icon: Mail },
    { to: "/admin/settings", label: "System Settings", icon: Settings },
  ],
  employee: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/profile", label: "My Profile", icon: ClipboardList },
  ],
  applicant: [
    { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { to: "/notifications", label: "Notifications", icon: Bell },
    { to: "/profile", label: "Account Settings", icon: FileSearch },
  ],
};

export const ROLE_ICON = { admin: ShieldCheck, employee: UserCog, applicant: Users } as const;
