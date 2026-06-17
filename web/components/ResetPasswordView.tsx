"use client";

import { useState } from "react";
import { call } from "@/lib/api";
import { Alert, Card, Field, PrimaryButton } from "@/components/ui";
import { Wordmark } from "@/components/Brand";
import ThemeToggle from "@/components/ThemeToggle";

// Shown when the app is opened from a Supabase recovery link. The recovery
// token (parsed from the URL hash by the parent) authorizes exactly one action:
// the holder setting their own new password. The token is never persisted.
export default function ResetPasswordView({
  token,
  onDone,
}: {
  token: string;
  onDone: (message: string) => void;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      return setError("Password must be at least 6 characters");
    }
    if (password !== confirm) {
      return setError("Passwords do not match");
    }
    setBusy(true);
    const r = await call<{ ok: boolean }>("POST", "/auth/update-password", {
      token,
      json: { password },
    });
    setBusy(false);
    if (r.error || !r.data?.ok) {
      return setError(
        r.error ?? "Could not update password. Request a fresh reset link.",
      );
    }
    onDone("Password updated. Please log in with your new password.");
  }

  return (
    <main className="relative grid min-h-dvh place-items-center px-4 py-10">
      <ThemeToggle className="absolute right-4 top-4" />
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <Wordmark className="text-5xl" />
          <p className="mt-3 text-sm font-medium uppercase tracking-[0.2em] text-faint">
            DocQA
          </p>
          <p className="mt-2 text-sm text-muted">Set a new password</p>
        </div>

        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            <Field
              label="New password"
              type="password"
              required
              minLength={6}
              autoComplete="new-password"
              placeholder="At least 6 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Field
              label="Confirm new password"
              type="password"
              required
              minLength={6}
              autoComplete="new-password"
              placeholder="Re-enter the password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />

            {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

            <PrimaryButton type="submit" loading={busy} className="w-full">
              Update password
            </PrimaryButton>
          </form>
        </Card>
      </div>
    </main>
  );
}
