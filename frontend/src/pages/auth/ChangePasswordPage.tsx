import { Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button } from "@/components/ui";
import PasswordChangeForm from "@/components/PasswordChangeForm";
import { useAuth } from "@/contexts/AuthContext";

/** Shown after first login when an administrator-provisioned password must be replaced. */
export default function ChangePasswordPage() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  if (loading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (!user.must_change_password) return <Navigate to="/dashboard" replace />;
  return (
    <AuthLayout title="Set a new password" subtitle="For security, you must replace the initial password before continuing.">
      <div className="space-y-4">
        <Alert kind="warning">You cannot use the application until your password is changed.</Alert>
        <PasswordChangeForm onDone={() => navigate("/dashboard", { replace: true })} />
        <Button variant="ghost" className="w-full" onClick={async () => { await logout(); navigate("/login"); }}>Sign out</Button>
      </div>
    </AuthLayout>
  );
}
