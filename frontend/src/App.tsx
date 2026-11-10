import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "@/layouts/AppLayout";
import { ProtectedRoute, PublicOnlyRoute } from "@/components/ProtectedRoute";
import { Spinner } from "@/components/ui";
import LoginPage from "@/pages/auth/LoginPage";
import RegisterPage from "@/pages/auth/RegisterPage";
import ForgotPasswordPage from "@/pages/auth/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/auth/ResetPasswordPage";
import VerifyEmailPage from "@/pages/auth/VerifyEmailPage";
import ChangePasswordPage from "@/pages/auth/ChangePasswordPage";
import NotificationsPage from "@/pages/NotificationsPage";
import ProfilePage from "@/pages/ProfilePage";
import NotFoundPage from "@/pages/NotFoundPage";

const DashboardPage = lazy(() => import("@/pages/DashboardPage"));
const EmployeesPage = lazy(() => import("@/pages/admin/EmployeesPage"));
const UsersPage = lazy(() => import("@/pages/admin/UsersPage"));
const AuditLogsPage = lazy(() => import("@/pages/admin/AuditLogsPage"));
const EmailLogsPage = lazy(() => import("@/pages/admin/EmailLogsPage"));
const SettingsPage = lazy(() => import("@/pages/admin/SettingsPage"));

export default function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        </Route>
        {/* Reachable whether or not signed in (links are opened from email) */}
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route element={<ProtectedRoute roles={["admin"]} />}>
              <Route path="/admin/employees" element={<EmployeesPage />} />
              <Route path="/admin/users" element={<UsersPage />} />
              <Route path="/admin/audit-logs" element={<AuditLogsPage />} />
              <Route path="/admin/email-logs" element={<EmailLogsPage />} />
              <Route path="/admin/settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
