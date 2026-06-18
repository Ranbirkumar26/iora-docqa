"use client";

import { useState } from "react";
import { AuthSession, call } from "@/lib/api";
import { Alert, Card, Field, PrimaryButton } from "@/components/ui";
import { Wordmark } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";

type Mode = "login" | "signup" | "reset";

export default function AuthView({
  onSession,
}: {
  onSession: (session: AuthSession) => void;
}) {
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setBusy(true);

    if (mode === "reset") {
      const r = await call<{ message?: string }>(
        "POST",
        "/auth/request-password-reset",
        { json: { email } },
      );
      setBusy(false);
      // generic confirmation regardless of whether the account exists
      setNotice(
        r.data?.message ??
          "If that email has an account, a reset link is on its way.",
      );
      return;
    }

    if (mode === "signup") {
      const r = await call<{ needs_confirmation?: boolean; message?: string }>(
        "POST",
        "/auth/signup",
        { json: { email, password } },
      );
      setBusy(false);
      if (r.error) return setError(r.error);
      // Unless the backend says confirmation is NOT required, do not auto-login.
      if (r.data?.needs_confirmation !== false) {
        setMode("login");
        setPassword("");
        setNotice(
          r.data?.message ??
            "Check your email to confirm your account, then log in.",
        );
        return;
      }
      setNotice("Account created. Logging you in...");
      // confirmation disabled -> fall through to login with same credentials
    }

    const r = await call<AuthSession>("POST", "/auth/login", {
      json: { email, password },
    });
    setBusy(false);
    if (r.error || !r.data) return setError(r.error ?? "Login failed");
    onSession(r.data);
  }

  async function resendConfirmation() {
    if (!email) return setError("Enter your email first");
    setError(null);
    setNotice(null);
    setBusy(true);
    const r = await call<{ message?: string }>("POST", "/auth/resend", {
      json: { email },
    });
    setBusy(false);
    setNotice(
      r.data?.message ??
        "If that account needs confirmation, a new email is on its way.",
    );
  }

  return (
    <main className="relative grid min-h-dvh place-items-center px-4 py-10">
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="w-full max-w-sm">
        {/* brand */}
        <div className="mb-8 text-center">
          <Wordmark className="text-5xl" />
          <p className="mt-3 text-sm font-medium uppercase tracking-[0.2em] text-faint">
            DocQA
          </p>
          <p className="mt-2 text-sm text-muted">
            Ask questions. Get answers from your documents.
          </p>
        </div>

        <Card className="p-6">
          {/* tab switch */}
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-inset p-1">
            {(["login", "signup"] as Mode[]).map((m) => (
              <button
                key={m}
                onClick={() => {
                  setMode(m);
                  setError(null);
                  setNotice(null);
                }}
                className={`min-h-10 rounded-lg text-sm font-medium transition ${
                  mode === m
                    ? "bg-panel text-fg shadow"
                    : "text-muted hover:text-fg"
                }`}
              >
                {m === "login" ? "Log in" : "Sign up"}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="space-y-4">
            <Field
              label="Email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            {mode !== "reset" && (
              <Field
                label="Password"
                type="password"
                required
                minLength={8}
                autoComplete={
                  mode === "login" ? "current-password" : "new-password"
                }
                placeholder={
                  mode === "signup" ? "8+ chars, letters and numbers" : "••••••••"
                }
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            )}

            {mode === "reset" && (
              <p className="text-xs text-muted">
                Enter your account email and we&apos;ll send a link to set a new
                password. The link goes only to your inbox.
              </p>
            )}

            {error && <Alert onClose={() => setError(null)}>{error}</Alert>}
            {notice && <Alert kind="ok">{notice}</Alert>}

            <PrimaryButton type="submit" loading={busy} className="w-full">
              {mode === "reset"
                ? "Send reset link"
                : mode === "login"
                  ? "Log in"
                  : "Create account"}
            </PrimaryButton>
          </form>

          {mode === "login" && (
            <div className="mt-4 flex flex-col items-center gap-1.5">
              <button
                type="button"
                onClick={() => {
                  setMode("reset");
                  setError(null);
                  setNotice(null);
                }}
                className="text-xs font-medium text-faint transition hover:text-fg"
              >
                Forgot password?
              </button>
              <button
                type="button"
                onClick={resendConfirmation}
                disabled={busy}
                className="text-xs font-medium text-faint transition hover:text-fg disabled:opacity-50"
              >
                Resend confirmation email
              </button>
            </div>
          )}
          {mode === "reset" && (
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setError(null);
                setNotice(null);
              }}
              className="mt-4 w-full text-center text-xs font-medium text-faint transition hover:text-fg"
            >
              Back to log in
            </button>
          )}
        </Card>

        <p className="mt-6 text-center text-xs text-faint">
          Your files stay private to your account.
        </p>
      </div>
    </main>
  );
}
