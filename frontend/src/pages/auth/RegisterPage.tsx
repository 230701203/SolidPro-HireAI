import { useState } from "react";
import { Link } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { MailCheck } from "lucide-react";
import AuthLayout from "@/layouts/AuthLayout";
import { Alert, Button, Field, PasswordInput, TextInput } from "@/components/ui";
import { api, errorMessage, fieldErrors } from "@/services/api";
import { mobileSchema, passwordSchema } from "@/utils/passwordRules";

const schema = z
  .object({
    full_name: z.string().trim().min(2, "Enter your full name"),
    email: z.string().min(1, "Enter your email").email("Enter a valid email"),
    mobile: z.string().optional(),
    password: passwordSchema,
    confirm: z.string(),
    accept_terms: z.boolean().refine((v) => v, "You must accept the privacy notice"),
  })
  .refine((d) => d.password === d.confirm, { path: ["confirm"], message: "Passwords do not match" });
type Form = z.infer<typeof schema>;

export default function RegisterPage() {
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    setError: setFieldError,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(schema), defaultValues: { accept_terms: false } });

  const onSubmit = async (v: Form) => {
    setError(null);
    if (v.mobile && !mobileSchema.safeParse(v.mobile).success) {
      setFieldError("mobile", { message: "Enter a valid mobile number" });
      return;
    }
    try {
      const { data } = await api.post<{ message: string }>("/auth/register", {
        full_name: v.full_name,
        email: v.email,
        mobile: v.mobile || null,
        password: v.password,
        accept_terms: v.accept_terms,
      });
      setDone(data.message);
    } catch (e) {
      const fe = fieldErrors(e);
      Object.entries(fe).forEach(([k, m]) => setFieldError(k as keyof Form, { message: m }));
      setError(errorMessage(e));
    }
  };

  if (done) {
    return (
      <AuthLayout title="Check your email" footer={<Link to="/login" className="font-medium text-brand-700 hover:underline">Back to sign in</Link>}>
        <div className="flex flex-col items-center gap-3 text-center">
          <MailCheck className="size-10 text-brand-600" aria-hidden />
          <p className="text-sm text-slate-600">{done}</p>
          <p className="text-xs text-slate-500">The link expires in 24 hours. Check your spam folder if you do not see it.</p>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Candidates register with a personal email. SolidPro employees use their company email and need administrator approval."
      footer={<>Already registered? <Link to="/login" className="font-medium text-brand-700 hover:underline">Sign in</Link></>}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
        {error && <Alert kind="error">{error}</Alert>}
        <Field label="Full name" htmlFor="full_name" error={errors.full_name?.message}>
          <TextInput id="full_name" autoComplete="name" invalid={!!errors.full_name} {...register("full_name")} />
        </Field>
        <Field label="Email address" htmlFor="email" error={errors.email?.message}>
          <TextInput id="email" type="email" autoComplete="email" invalid={!!errors.email} {...register("email")} />
        </Field>
        <Field label="Mobile number" htmlFor="mobile" error={errors.mobile?.message} hint="Required for applicants. Optional for company email accounts.">
          <TextInput id="mobile" type="tel" autoComplete="tel" placeholder="+91 98765 43210" invalid={!!errors.mobile} {...register("mobile")} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password?.message} hint="10+ characters with upper-case, lower-case and a number.">
          <PasswordInput id="password" autoComplete="new-password" invalid={!!errors.password} {...register("password")} />
        </Field>
        <Field label="Confirm password" htmlFor="confirm" error={errors.confirm?.message}>
          <PasswordInput id="confirm" autoComplete="new-password" invalid={!!errors.confirm} {...register("confirm")} />
        </Field>
        <div>
          <label className="flex items-start gap-2 text-sm text-slate-700">
            <input type="checkbox" className="mt-0.5 size-4 rounded border-slate-300" {...register("accept_terms")} />
            <span>I consent to SolidPro processing my personal data, including AI-assisted resume analysis and assessment recording, for recruitment purposes.</span>
          </label>
          {errors.accept_terms && <p role="alert" className="mt-1 text-xs text-red-600">{errors.accept_terms.message}</p>}
        </div>
        <Button type="submit" loading={isSubmitting} className="w-full">Create account</Button>
      </form>
    </AuthLayout>
  );
}
