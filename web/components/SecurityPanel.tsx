"use client";

import { useCallback, useEffect, useState } from "react";
import { call, MfaEnroll, MfaFactor } from "@/lib/api";
import { Alert, Card, Field, GhostButton, PrimaryButton } from "@/components/ui";

// Account security: change password, two-factor (TOTP), logout-all, delete.
export default function SecurityPanel({
  token,
  refreshToken,
  onAuthExpired,
  onAccountDeleted,
}: {
  token: string;
  refreshToken: string;
  onAuthExpired: () => void;
  onAccountDeleted: () => void;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null,
  );

  const [loggingOut, setLoggingOut] = useState(false);

  const [factors, setFactors] = useState<MfaFactor[]>([]);
  const [enroll, setEnroll] = useState<MfaEnroll | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [mfaBusy, setMfaBusy] = useState(false);
  const [mfaMsg, setMfaMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null,
  );

  const [showDelete, setShowDelete] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const mfaEnabled = factors.some((f) => f.status === "verified");

  const loadFactors = useCallback(async () => {
    const r = await call<{ factors: MfaFactor[] }>("POST", "/auth/mfa/factors", {
      token,
      json: { refresh_token: refreshToken },
    });
    if (r.data) setFactors(r.data.factors);
  }, [token, refreshToken]);

  useEffect(() => {
    loadFactors();
  }, [loadFactors]);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (next.length < 8) {
      return setMsg({
        kind: "error",
        text: "New password must be at least 8 characters, with letters and numbers",
      });
    }
    if (next !== confirm) {
      return setMsg({ kind: "error", text: "New passwords do not match" });
    }
    setBusy(true);
    const r = await call<{ ok: boolean }>("POST", "/auth/change-password", {
      token,
      json: { current_password: current, new_password: next },
    });
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data?.ok) {
      return setMsg({ kind: "error", text: r.error ?? "Could not change password" });
    }
    setMsg({ kind: "ok", text: "Password changed." });
    setCurrent("");
    setNext("");
    setConfirm("");
  }

  async function logoutAll() {
    setLoggingOut(true);
    const r = await call<{ ok: boolean }>("POST", "/auth/logout-all", { token });
    setLoggingOut(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data?.ok) {
      return setMsg({ kind: "error", text: r.error ?? "Could not sign out everywhere" });
    }
    onAuthExpired(); // current session is now revoked -> force re-login
  }

  async function startEnroll() {
    setMfaMsg(null);
    setMfaBusy(true);
    const r = await call<MfaEnroll>("POST", "/auth/mfa/enroll", {
      token,
      json: { refresh_token: refreshToken },
    });
    setMfaBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) {
      return setMfaMsg({ kind: "error", text: r.error ?? "Could not start enrollment" });
    }
    setEnroll(r.data);
    setMfaCode("");
  }

  async function verifyEnroll(e: React.FormEvent) {
    e.preventDefault();
    if (!enroll) return;
    setMfaMsg(null);
    setMfaBusy(true);
    const r = await call<{ access_token?: string }>("POST", "/auth/mfa/verify", {
      token,
      json: {
        factor_id: enroll.factor_id,
        code: mfaCode.trim(),
        refresh_token: refreshToken,
      },
    });
    setMfaBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setMfaMsg({ kind: "error", text: r.error });
    setEnroll(null);
    setMfaCode("");
    setMfaMsg({ kind: "ok", text: "Two-factor enabled." });
    loadFactors();
  }

  async function disableMfa() {
    const verified = factors.find((f) => f.status === "verified");
    if (!verified) return;
    setMfaMsg(null);
    setMfaBusy(true);
    const r = await call<{ ok: boolean }>("POST", "/auth/mfa/unenroll", {
      token,
      json: { factor_id: verified.id, refresh_token: refreshToken },
    });
    setMfaBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setMfaMsg({ kind: "error", text: r.error });
    setMfaMsg({ kind: "ok", text: "Two-factor disabled." });
    loadFactors();
  }

  async function deleteAccount() {
    setDeleteErr(null);
    setDeleting(true);
    const r = await call<{ deleted: boolean }>("DELETE", "/account", { token });
    setDeleting(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data?.deleted) {
      return setDeleteErr(r.error ?? "Could not delete account");
    }
    onAccountDeleted();
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Security
        </h3>
        <Card className="p-3">
          <form onSubmit={changePassword} className="space-y-3">
            <Field
              label="Current password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              required
            />
            <Field
              label="New password"
              type="password"
              minLength={8}
              autoComplete="new-password"
              placeholder="8+ chars, letters and numbers"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            <Field
              label="Confirm new password"
              type="password"
              minLength={8}
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
            />
            {msg && (
              <Alert kind={msg.kind} onClose={() => setMsg(null)}>
                {msg.text}
              </Alert>
            )}
            <PrimaryButton
              type="submit"
              loading={busy}
              disabled={!current || !next}
              className="w-full !min-h-9 text-xs"
            >
              Change password
            </PrimaryButton>
          </form>
          <div className="mt-3 border-t border-edge pt-3">
            <GhostButton
              onClick={logoutAll}
              disabled={loggingOut}
              className="!min-h-9 w-full text-xs"
            >
              {loggingOut ? "Signing out..." : "Log out all devices"}
            </GhostButton>
          </div>
        </Card>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Two-factor authentication
        </h3>
        <Card className="space-y-3 p-3">
          {mfaEnabled ? (
            <>
              <p className="text-xs text-muted">
                Two-factor is{" "}
                <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                  on
                </span>
                . You&apos;ll enter a code from your authenticator at login.
              </p>
              <GhostButton
                onClick={disableMfa}
                disabled={mfaBusy}
                className="!min-h-9 w-full text-xs"
              >
                Disable two-factor
              </GhostButton>
            </>
          ) : enroll ? (
            <form onSubmit={verifyEnroll} className="space-y-2.5">
              <p className="text-xs leading-relaxed text-muted">
                Scan the QR (or enter the secret) in your authenticator app, then
                enter the 6-digit code to confirm.
              </p>
              {enroll.qr_code && enroll.qr_code.startsWith("data:") && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={enroll.qr_code}
                  alt="Two-factor QR code"
                  className="mx-auto h-40 w-40 rounded bg-white p-1"
                />
              )}
              {enroll.secret && (
                <code className="block break-all rounded bg-inset px-2 py-1 text-[11px] text-muted">
                  {enroll.secret}
                </code>
              )}
              <input
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder="123456"
                className="min-h-9 w-full rounded-xl border border-edge-strong bg-field px-3 text-sm text-fg placeholder-faint transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
              />
              <div className="grid grid-cols-2 gap-2">
                <GhostButton
                  onClick={() => {
                    setEnroll(null);
                    setMfaCode("");
                  }}
                  className="!min-h-9 text-xs"
                >
                  Cancel
                </GhostButton>
                <PrimaryButton
                  type="submit"
                  loading={mfaBusy}
                  className="!min-h-9 text-xs"
                >
                  Verify &amp; enable
                </PrimaryButton>
              </div>
            </form>
          ) : (
            <GhostButton
              onClick={startEnroll}
              disabled={mfaBusy}
              className="!min-h-9 w-full text-xs"
            >
              Enable two-factor
            </GhostButton>
          )}
          {mfaMsg && (
            <Alert kind={mfaMsg.kind} onClose={() => setMfaMsg(null)}>
              {mfaMsg.text}
            </Alert>
          )}
        </Card>
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-red-600 dark:text-red-400">
          Danger zone
        </h3>
        <Card className="space-y-3 border-red-500/30 p-3">
          {!showDelete ? (
            <GhostButton
              onClick={() => setShowDelete(true)}
              className="!min-h-9 w-full border-red-500/40 text-xs text-red-600 hover:bg-red-500/10 dark:text-red-400"
            >
              Delete my account
            </GhostButton>
          ) : (
            <div className="space-y-2.5">
              <p className="text-xs leading-relaxed text-muted">
                Permanently deletes your account, files, reports, conversation,
                and memory. This cannot be undone. Type{" "}
                <span className="font-semibold text-fg">DELETE</span> to confirm.
              </p>
              <input
                value={deleteText}
                onChange={(e) => setDeleteText(e.target.value)}
                placeholder="DELETE"
                className="min-h-9 w-full rounded-xl border border-edge-strong bg-field px-3 text-sm text-fg placeholder-faint transition focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
              />
              {deleteErr && <Alert onClose={() => setDeleteErr(null)}>{deleteErr}</Alert>}
              <div className="grid grid-cols-2 gap-2">
                <GhostButton
                  onClick={() => {
                    setShowDelete(false);
                    setDeleteText("");
                    setDeleteErr(null);
                  }}
                  className="!min-h-9 text-xs"
                >
                  Cancel
                </GhostButton>
                <button
                  onClick={deleteAccount}
                  disabled={deleteText !== "DELETE" || deleting}
                  className="inline-flex min-h-9 items-center justify-center rounded-xl bg-red-600 px-3 text-xs font-semibold text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {deleting ? "Deleting..." : "Permanently delete"}
                </button>
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
