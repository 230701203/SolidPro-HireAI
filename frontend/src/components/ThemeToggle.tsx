import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const KEY = "solid-hire-theme";

function initial(): boolean {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark") return true;
    if (saved === "light") return false;
  } catch { /* storage can be blocked; fall through to the system setting */ }
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Light/dark switch. The choice is remembered in this browser; until it is made, the system setting is followed. */
export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [dark, setDark] = useState(initial);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const flip = () => {
    const next = !dark;
    setDark(next);
    try { localStorage.setItem(KEY, next ? "dark" : "light"); } catch { /* not saved, still applied */ }
  };

  return (
    <button type="button" role="switch" aria-checked={dark} aria-label="Dark mode" title={dark ? "Switch to light mode" : "Switch to dark mode"} onClick={flip}
      className={`rounded-lg p-2 text-slate-600 hover:bg-slate-100 ${className}`}>
      {dark ? <Sun className="size-5" aria-hidden /> : <Moon className="size-5" aria-hidden />}
    </button>
  );
}
