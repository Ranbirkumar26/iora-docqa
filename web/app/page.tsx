"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AuthView from "@/components/AuthView";
import ResetPasswordView from "@/components/ResetPasswordView";
import Dashboard from "@/components/Dashboard";
import { Spinner } from "@/components/ui";
import { AuthSession, call, configureAuthRefresh } from "@/lib/api";
import { clearDocqaSessionState } from "@/lib/session-state";

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
  const [recoveryToken, setRecoveryToken] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState<string | null>(null);
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
      clearDocqaSessionState();
    }
    setSession(next);
  }, []);

  // Supabase auth links (recovery / email confirmation) land here with the
  // session in the URL hash. Capture it, then strip it from the address bar /
  // history so the token isn't left lying around. Placed after `save` so a
  // confirmation link can establish a session.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash;
    if (!hash.includes("access_token")) return;
    const params = new URLSearchParams(hash.replace(/^#/, ""));
    const accessToken = params.get("access_token");
    const type = params.get("type");
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
    if (!accessToken) return;
    if (type === "recovery") {
      setRecoveryToken(accessToken);
      return;
    }
    // email confirmation / magic link -> establish a logged-in session
    const expiresAt = params.get("expires_at");
    save({
      access_token: accessToken,
      refresh_token: params.get("refresh_token"),
      expires_at: expiresAt ? Number(expiresAt) : null,
    });
    setAuthNotice("Email confirmed — you're logged in.");
  }, [save]);

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

  if (recoveryToken) {
    return (
      <ResetPasswordView
        token={recoveryToken}
        onDone={(msg) => {
          setRecoveryToken(null);
          setAuthNotice(msg);
          save(null);
        }}
      />
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
        {authNotice && (
          <p className="bg-emerald-500/15 px-4 py-2 text-center text-xs text-emerald-700 dark:text-emerald-300">
            {authNotice}
          </p>
        )}
        <AuthView
          onSession={(next) => {
            setExpiredMsg(false);
            setAuthNotice(null);
            save(next);
          }}
        />
      </>
    );
  }

  return (
    <Dashboard
      token={session.access_token}
      refreshToken={session.refresh_token ?? ""}
      onLogout={() => {
        setExpiredMsg(false);
        save(null);
      }}
      onAuthExpired={authExpired}
    />
  );
}
