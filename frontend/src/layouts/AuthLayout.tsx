import type { ReactNode } from "react";

export default function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-full items-center justify-center bg-gradient-to-br from-brand-50 via-slate-50 to-slate-100 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex flex-col items-center text-center">
          <span className="mb-3 flex size-12 items-center justify-center rounded-xl bg-brand-700 text-2xl font-bold text-white">S</span>
          <p className="text-sm font-semibold text-slate-900">SolidPro HireAI</p>
          <p className="text-xs text-slate-500">SolidPro Engineering Support Pvt Ltd</p>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm sm:p-8">
          <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
        {footer && <div className="mt-5 text-center text-sm text-slate-600">{footer}</div>}
      </div>
    </div>
  );
}
