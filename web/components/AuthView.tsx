"use client";

import { useState } from "react";
import { AuthSession, call } from "@/lib/api";
import { Alert, Card, Field, PrimaryButton } from "@/components/ui";
import { Wordmark } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";

type Mode = "login" | "signup";

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

    if (mode === "signup") {
      const r = await call<{ user_id: string }>("POST", "/auth/signup", {
        json: { email, password },
      });
      setBusy(false);
      if (r.error) return setError(r.error);
      setNotice("Account created. Logging you in...");
      // fall through to login with same credentials
    }

    const r = await call<AuthSession>("POST", "/auth/login", {
      json: { email, password },
    });
    setBusy(false);
    if (r.error || !r.data) return setError(r.error ?? "Login failed");
    onSession(r.data);
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
            <Field
              label="Password"
              type="password"
              required
              minLength={6}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              placeholder={mode === "signup" ? "At least 6 characters" : "••••••••"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />

            {error && <Alert onClose={() => setError(null)}>{error}</Alert>}
            {notice && <Alert kind="ok">{notice}</Alert>}

            <PrimaryButton type="submit" loading={busy} className="w-full">
              {mode === "login" ? "Log in" : "Create account"}
            </PrimaryButton>
          </form>
        </Card>

        <p className="mt-6 text-center text-xs text-faint">
          Your files stay private to your account.
        </p>
      </div>
    </main>
  );
}
