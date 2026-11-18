import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button, Field, PasswordInput, TextInput } from "@/components/ui";
import { useAuth } from "@/contexts/AuthContext";
import { api, errorCode, errorMessage } from "@/services/api";
import { useToast } from "@/components/Toast";
import { LiveHint } from "@/components/LiveChecks";
import { LIMITS, emailProblem, emailSchema } from "@/utils/validation";

const schema = z.object({
  email: emailSchema,
  // Sign-in only checks presence and length: it must never reject an existing account over a newer password rule.
  password: z.string().min(1, "Enter your password").max(LIMITS.loginPasswordMax, `Password must be at most ${LIMITS.loginPasswordMax} characters`),
  remember_me: z.boolean(),
});
type Form = z.infer<typeof schema>;

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [error, setError] = useState<{ code?: string; message: string } | null>(null);
  const {
    register,
    handleSubmit,
    getValues,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema), mode: "onChange", defaultValues: { remember_me: false } });
  const emailValue = watch("email") ?? "";

  const onSubmit = async (v: Form) => {
    setError(null);
    try {
      const user = await login(v.email, v.password, v.remember_me);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(user.must_change_password ? "/change-password" : from && from !== "/login" ? from : "/dashboard", { replace: true });
    } catch (e) {
      setError({ code: errorCode(e), message: errorMessage(e) });
    }
  };

  const resend = async () => {
    try {
      await api.post("/auth/resend-verification", { email: getValues("email") });
      toast.success("If the account exists, a new verification email is on its way.");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Use your Solid HIRE account."
      footer={
        <>
          New candidate? <Link to="/register" className="font-medium text-brand-700 hover:underline">Create an applicant account</Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && (
          <Alert kind={error.code === "pending_approval" ? "warning" : "error"}>
            {error.message}
            {error.code === "email_not_verified" && (
              <button type="button" onClick={resend} className="ml-1 font-medium underline">Resend verification email</button>
            )}
          </Alert>
        )}
        <Field label="Email address" htmlFor="email" error={errors.email?.message}>
          <TextInput id="email" type="email" autoComplete="username" maxLength={LIMITS.emailMax} invalid={!!errors.email} {...register("email")} />
          {!errors.email && <LiveHint value={emailValue} problem={emailProblem(emailValue)} okText="Email format looks good" />}
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message}>
          <PasswordInput id="password" autoComplete="current-password" maxLength={LIMITS.loginPasswordMax} invalid={!!errors.password} {...register("password")} />
        </Field>
        <div className="flex items-center justify-between text-sm">
          <label className="flex items-center gap-2 text-slate-700">
            <input type="checkbox" className="size-4 rounded border-slate-300" {...register("remember_me")} /> Remember me
          </label>
          <Link to="/forgot-password" className="font-medium text-brand-700 hover:underline">Forgot password?</Link>
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">Sign in</Button>
      </form>
    </AuthLayout>
  );
}
