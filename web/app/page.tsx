"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AuthView from "@/components/AuthView";
import Dashboard from "@/components/Dashboard";
import { Spinner } from "@/components/ui";
import { AuthSession, call, configureAuthRefresh } from "@/lib/api";

const SESSION_KEY = "docqa_session";
const LEGACY_TOKEN_KEY = "docqa_token";

function readStoredSession(): AuthSession | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as AuthSession;
      if (parsed?.access_token) return parsed;
    } catch {
      localStorage.removeItem(SESSION_KEY);
    }
  }

  const legacyToken = localStorage.getItem(LEGACY_TOKEN_KEY);
  return legacyToken ? { access_token: legacyToken, refresh_token: null } : null;
}

export default function Home() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [ready, setReady] = useState(false);
  const [expiredMsg, setExpiredMsg] = useState(false);
  const sessionRef = useRef<AuthSession | null>(null);
  const refreshPromiseRef = useRef<Promise<string | null> | null>(null);

  useEffect(() => {
    const stored = readStoredSession();
    sessionRef.current = stored;
    setSession(stored);
    setReady(true);
  }, []);

  const save = useCallback((next: AuthSession | null) => {
    sessionRef.current = next;
    if (next?.access_token) {
      localStorage.setItem(SESSION_KEY, JSON.stringify(next));
      localStorage.removeItem(LEGACY_TOKEN_KEY);
    } else {
      localStorage.removeItem(SESSION_KEY);
      localStorage.removeItem(LEGACY_TOKEN_KEY);
    }
    setSession(next);
  }, []);

  const authExpired = useCallback(() => {
    save(null);
    setExpiredMsg(true);
  }, [save]);

  useEffect(() => {
    configureAuthRefresh(async (failedToken) => {
      const current = sessionRef.current;
      if (!current?.refresh_token) return null;
      if (current.access_token !== failedToken) return current.access_token;

      if (!refreshPromiseRef.current) {
        refreshPromiseRef.current = (async () => {
          const r = await call<AuthSession>("POST", "/auth/refresh", {
            json: { refresh_token: current.refresh_token },
          });
          if (r.data?.access_token) {
            save(r.data);
            return r.data.access_token;
          }
          return null;
        })().finally(() => {
          refreshPromiseRef.current = null;
        });
      }
      return refreshPromiseRef.current;
    });

    return () => configureAuthRefresh(null);
  }, [save]);

  if (!ready) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner className="h-6 w-6 text-faint" />
      </div>
    );
  }

  if (!session?.access_token) {
    return (
      <>
        {expiredMsg && (
          <p className="bg-amber-500/15 px-4 py-2 text-center text-xs text-amber-700 dark:text-amber-300">
            Your session expired. Please log in again.
          </p>
        )}
        <AuthView
          onSession={(next) => {
            setExpiredMsg(false);
            save(next);
          }}
        />
      </>
    );
  }

  return (
    <Dashboard
      token={session.access_token}
      onLogout={() => {
        setExpiredMsg(false);
        save(null);
      }}
      onAuthExpired={authExpired}
    />
  );
}
