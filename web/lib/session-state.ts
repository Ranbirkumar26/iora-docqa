"use client";

import { useEffect, useState } from "react";

export function useSessionState<T>(key: string, initialValue: T) {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return initialValue;
    try {
      const raw = window.sessionStorage.getItem(key);
      return raw ? (JSON.parse(raw) as T) : initialValue;
    } catch {
      window.sessionStorage.removeItem(key);
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* sessionStorage may be unavailable in restricted browser modes */
    }
  }, [key, value]);

  return [value, setValue] as const;
}

export function clearDocqaSessionState() {
  if (typeof window === "undefined") return;
  try {
    for (let i = window.sessionStorage.length - 1; i >= 0; i -= 1) {
      const key = window.sessionStorage.key(i);
      if (key?.startsWith("docqa:")) window.sessionStorage.removeItem(key);
    }
  } catch {
    /* sessionStorage may be unavailable in restricted browser modes */
  }
}
