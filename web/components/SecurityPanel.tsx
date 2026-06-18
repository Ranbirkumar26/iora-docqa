"use client";

import { useState } from "react";
import { call } from "@/lib/api";
import { Alert, Card, Field, GhostButton, PrimaryButton } from "@/components/ui";

// Account security: change password (re-auth with current password server-side)
// and a danger-zone account deletion.
export default function SecurityPanel({
  token,
  onAuthExpired,
  onAccountDeleted,
}: {
  token: string;
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

  const [showDelete, setShowDelete] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  async function changePassword(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (next.length < 6) {
      return setMsg({ kind: "error", text: "New password must be at least 6 characters" });
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
              minLength={6}
              autoComplete="new-password"
              placeholder="At least 6 characters"
              value={next}
              onChange={(e) => setNext(e.target.value)}
              required
            />
            <Field
              label="Confirm new password"
              type="password"
              minLength={6}
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
