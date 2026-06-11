"use client";

import { useState } from "react";
import { call } from "@/lib/api";
import { Alert, Card, Field, PrimaryButton } from "@/components/ui";

type Mode = "login" | "signup";

export default function AuthView({
  onToken,
}: {
  onToken: (token: string) => void;
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
      setNotice("Account created — logging you in…");
      // fall through to login with same credentials
    }

    const r = await call<{ access_token: string }>("POST", "/auth/login", {
      json: { email, password },
    });
    setBusy(false);
    if (r.error || !r.data) return setError(r.error ?? "Login failed");
    onToken(r.data.access_token);
  }

  return (
    <main className="grid min-h-dvh place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        {/* brand */}
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-indigo-500 to-violet-600 text-2xl shadow-lg shadow-indigo-950/50">
            📄
          </div>
          <h1 className="text-2xl font-bold tracking-tight">DocQA</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Ask questions. Get answers from <em>your</em> documents.
          </p>
        </div>

        <Card className="p-6">
          {/* tab switch */}
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-zinc-800/80 p-1">
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
                    ? "bg-zinc-950 text-white shadow"
                    : "text-zinc-400 hover:text-zinc-200"
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

        <p className="mt-6 text-center text-xs text-zinc-500">
          Your files stay private to your account.
        </p>
      </div>
    </main>
  );
}
