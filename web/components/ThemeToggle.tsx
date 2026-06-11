"use client";

import { useEffect, useState } from "react";
import { IconMoon, IconSun } from "@/components/icons";

const KEY = "docqa_theme";

export default function ThemeToggle({ className = "" }: { className?: string }) {
  const [dark, setDark] = useState<boolean | null>(null);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem(KEY, next ? "dark" : "light");
    } catch {
      /* private mode */
    }
    setDark(next);
  }

  return (
    <button
      onClick={toggle}
      className={`grid min-h-9 min-w-9 place-items-center rounded-lg border border-edge bg-panel text-muted transition hover:text-fg ${className}`}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      title={dark ? "Light mode" : "Dark mode"}
    >
      {dark === null ? null : dark ? <IconSun /> : <IconMoon />}
    </button>
  );
}
