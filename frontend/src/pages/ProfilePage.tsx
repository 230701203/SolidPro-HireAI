import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useAuth } from "@/contexts/AuthContext";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { Alert, Button, Card, Field, PageHeader, RoleBadge, StatusBadge, TextInput } from "@/components/ui";
import PasswordChangeForm from "@/components/PasswordChangeForm";
import { useToast } from "@/components/Toast";
import { formatDateTime } from "@/utils/format";
import { mobileSchema } from "@/utils/passwordRules";
import type { User } from "@/types";

const schema = z.object({
  full_name: z.string().trim().min(2, "Enter your full name"),
  mobile: z.union([mobileSchema, z.literal("")]),
});
type Form = z.infer<typeof schema>;

export default function ProfilePage() {
  const { user, setUser } = useAuth();
  const toast = useToast();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError: setFieldError,
    formState: { errors, isSubmitting, isDirty },
    reset,
  } = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { full_name: user?.full_name ?? "", mobile: user?.mobile ?? "" } });

  if (!user) return null;

  const onSubmit = async (v: Form) => {
    setError(null);
    try {
      const { data } = await api.patch<User>("/auth/me", { full_name: v.full_name, mobile: v.mobile || null });
      setUser(data);
      reset({ full_name: data.full_name, mobile: data.mobile ?? "" });
      toast.success("Profile updated.");
    } catch (e) {
      Object.entries(fieldErrors(e)).forEach(([k, m]) => setFieldError(k as keyof Form, { message: m }));
      setError(errorMessage(e));
    }
  };

  return (
    <>
      <PageHeader title="My account" description="Your details and security settings." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="p-6">
          <h2 className="mb-4 font-semibold text-slate-900">Profile</h2>
          <dl className="mb-5 grid grid-cols-2 gap-3 text-sm">
            <dt className="text-slate-500">Email</dt><dd className="truncate">{user.email}</dd>
            <dt className="text-slate-500">Account type</dt><dd><RoleBadge role={user.role} /></dd>
            <dt className="text-slate-500">Status</dt><dd><StatusBadge status={user.status} /></dd>
            <dt className="text-slate-500">Last sign-in</dt><dd>{formatDateTime(user.last_login_at)}</dd>
          </dl>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {error && <Alert kind="error">{error}</Alert>}
            <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
              <TextInput id="full_name" invalid={!!errors.full_name} {...register("full_name")} />
            </Field>
            <Field label="Mobile number" htmlFor="mobile" error={errors.mobile?.message}>
              <TextInput id="mobile" type="tel" invalid={!!errors.mobile} {...register("mobile")} />
            </Field>
            <Button type="submit" loading={isSubmitting} disabled={!isDirty}>Save changes</Button>
          </form>
        </Card>
        <Card className="p-6">
          <h2 className="mb-4 font-semibold text-slate-900">Change password</h2>
          <PasswordChangeForm />
        </Card>
      </div>
    </>
  );
}
