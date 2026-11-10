import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Spinner } from "@/components/ui";
import type { Role } from "@/types";

/**
 * Client-side route guard (UX only - the API enforces every rule again on the server).
 * - not signed in            -> /login
 * - must change password     -> /change-password
 * - wrong account type       -> /dashboard
 */
export function ProtectedRoute({ roles }: { roles?: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Checking your session…" />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (user.must_change_password) return <Navigate to="/change-password" replace />;
  if (roles && !roles.includes(user.role)) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

/** Wraps public pages (login/register). Signed-in users are sent to their dashboard. */
export function PublicOnlyRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Loading…" />;
  if (user) return <Navigate to={user.must_change_password ? "/change-password" : "/dashboard"} replace />;
  return <Outlet />;
}
