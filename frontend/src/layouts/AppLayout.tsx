import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bell, ChevronDown, KeyRound, LogOut, Menu, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/services/api";
import { NAV } from "./navigation";
import { RoleBadge } from "@/components/ui";

function Logo() {
  return (
    <Link to="/dashboard" className="flex items-center gap-2.5">
      <span className="flex size-9 items-center justify-center rounded-lg bg-brand-700 text-lg font-bold text-white">S</span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-slate-900">SolidPro HireAI</span>
        <span className="block text-[11px] text-slate-500">Engineering Support Pvt Ltd</span>
      </span>
    </Link>
  );
}

function NotificationBell() {
  const { data } = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: async () => (await api.get<{ count: number }>("/notifications/unread-count")).data.count,
    refetchInterval: 30_000,
  });
  return (
    <Link to="/notifications" aria-label={`Notifications${data ? `, ${data} unread` : ""}`} className="relative rounded-lg p-2 text-slate-600 hover:bg-slate-100">
      <Bell className="size-5" />
      {!!data && (
        <span className="absolute right-0.5 top-0.5 flex min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-4 text-white">
          {data > 99 ? "99+" : data}
        </span>
      )}
    </Link>
  );
}

function ProfileMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const close = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  if (!user) return null;
  const initials = user.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open} className="flex items-center gap-2 rounded-lg p-1.5 hover:bg-slate-100">
        <span className="flex size-8 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-800">{initials}</span>
        <span className="hidden text-left sm:block">
          <span className="block text-sm font-medium leading-tight text-slate-900">{user.full_name}</span>
          <span className="block text-xs text-slate-500">{user.email}</span>
        </span>
        <ChevronDown className="size-4 text-slate-500" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 z-40 mt-2 w-60 rounded-xl border border-slate-200 bg-white p-1.5 shadow-lg">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{user.full_name}</p>
            <div className="mt-1"><RoleBadge role={user.role} /></div>
          </div>
          <hr className="my-1 border-slate-100" />
          <button role="menuitem" onClick={() => { setOpen(false); navigate("/profile"); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm hover:bg-slate-50">
            <KeyRound className="size-4" /> Account &amp; password
          </button>
          <button role="menuitem" onClick={async () => { await logout(); navigate("/login"); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-red-600 hover:bg-red-50">
            <LogOut className="size-4" /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export default function AppLayout() {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);
  if (!user) return null;
  const items = NAV[user.role];

  const nav = (
    <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4" aria-label="Main">
      {items.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
              isActive ? "bg-brand-50 text-brand-800" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            }`
          }
        >
          <Icon className="size-[18px]" aria-hidden /> {label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="flex h-full">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="border-b border-slate-200 px-5 py-4"><Logo /></div>
        {nav}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="relative flex h-full w-72 flex-col bg-white shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <Logo />
              <button onClick={() => setMobileOpen(false)} aria-label="Close menu"><X className="size-5" /></button>
            </div>
            {nav}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <button className="rounded-lg p-2 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <div className="flex-1" />
          <NotificationBell />
          <ProfileMenu />
        </header>
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8">
          <div className="mx-auto max-w-6xl"><Outlet /></div>
        </main>
      </div>
    </div>
  );
}
