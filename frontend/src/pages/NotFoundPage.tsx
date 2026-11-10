import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="text-5xl font-semibold text-brand-700">404</p>
      <p className="text-slate-600">This page does not exist.</p>
      <Link to="/dashboard" className="rounded-lg bg-brand-700 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-800">Go to dashboard</Link>
    </div>
  );
}
