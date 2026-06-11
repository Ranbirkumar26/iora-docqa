"use client";

import { useCallback, useEffect, useState } from "react";
import AuthView from "@/components/AuthView";
import Dashboard from "@/components/Dashboard";
import { Spinner } from "@/components/ui";

const TOKEN_KEY = "docqa_token";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [expiredMsg, setExpiredMsg] = useState(false);

  useEffect(() => {
    setToken(localStorage.getItem(TOKEN_KEY));
    setReady(true);
  }, []);

  const save = useCallback((t: string | null) => {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
    setToken(t);
  }, []);

  const authExpired = useCallback(() => {
    save(null);
    setExpiredMsg(true);
  }, [save]);

  if (!ready) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner className="h-6 w-6 text-zinc-500" />
      </div>
    );
  }

  if (!token) {
    return (
      <>
        {expiredMsg && (
          <p className="bg-amber-500/15 px-4 py-2 text-center text-xs text-amber-300">
            Your session expired — please log in again.
          </p>
        )}
        <AuthView
          onToken={(t) => {
            setExpiredMsg(false);
            save(t);
          }}
        />
      </>
    );
  }

  return (
    <Dashboard token={token} onLogout={() => save(null)} onAuthExpired={authExpired} />
  );
}
