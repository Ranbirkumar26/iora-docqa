"use client";

import { useCallback, useEffect, useState } from "react";
import { call, Profile } from "@/lib/api";
import { Alert, Card, Field, PrimaryButton } from "@/components/ui";

const GENDERS = ["", "Male", "Female", "Non-binary", "Other", "Prefer not to say"];

const labelCls =
  "mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted";
const inputCls =
  "min-h-11 w-full rounded-xl border border-edge-strong bg-field px-3.5 py-2.5 text-sm text-fg placeholder-faint transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30";

export default function ProfilePanel({
  token,
  onAuthExpired,
}: {
  token: string;
  onAuthExpired: () => void;
}) {
  const [p, setP] = useState<Profile>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ kind: "ok" | "error"; text: string } | null>(
    null,
  );

  const load = useCallback(async () => {
    const r = await call<{ profile: Profile }>("GET", "/profile", { token });
    if (r.status === 401) return onAuthExpired();
    if (r.data?.profile) setP(r.data.profile);
  }, [token, onAuthExpired]);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    setBusy(true);
    const r = await call<{ profile: Profile }>("PUT", "/profile", {
      token,
      json: {
        full_name: p.full_name || null,
        gender: p.gender || null,
        age: p.age ?? null,
        phone: p.phone || null,
        city: p.city || null,
        country: p.country || null,
        bio: p.bio || null,
      },
    });
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setMsg({ kind: "error", text: r.error });
    if (r.data?.profile) setP(r.data.profile);
    setMsg({ kind: "ok", text: "Profile saved." });
  }

  return (
    <div>
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
        About you
      </h3>
      <Card className="p-4">
        <form onSubmit={save} className="space-y-3">
          <Field
            label="Full name"
            maxLength={100}
            placeholder="Your name"
            value={p.full_name ?? ""}
            onChange={(e) => setP((v) => ({ ...v, full_name: e.target.value }))}
          />
          <label className="block">
            <span className={labelCls}>Gender</span>
            <select
              className={inputCls}
              value={p.gender ?? ""}
              onChange={(e) => setP((v) => ({ ...v, gender: e.target.value }))}
            >
              {GENDERS.map((g) => (
                <option key={g} value={g}>
                  {g || "Prefer not to say"}
                </option>
              ))}
            </select>
          </label>
          <Field
            label="Age"
            type="number"
            min={13}
            max={120}
            placeholder="13–120"
            value={p.age ?? ""}
            onChange={(e) =>
              setP((v) => ({
                ...v,
                age: e.target.value === "" ? null : Number(e.target.value),
              }))
            }
          />
          <Field
            label="Phone"
            type="tel"
            maxLength={30}
            placeholder="+1 555 123 4567"
            value={p.phone ?? ""}
            onChange={(e) => setP((v) => ({ ...v, phone: e.target.value }))}
          />
          <Field
            label="Current city"
            maxLength={100}
            value={p.city ?? ""}
            onChange={(e) => setP((v) => ({ ...v, city: e.target.value }))}
          />
          <Field
            label="Country"
            maxLength={100}
            value={p.country ?? ""}
            onChange={(e) => setP((v) => ({ ...v, country: e.target.value }))}
          />
          <label className="block">
            <span className={labelCls}>About</span>
            <textarea
              className={`${inputCls} min-h-20 resize-none`}
              maxLength={1000}
              placeholder="A short bio"
              value={p.bio ?? ""}
              onChange={(e) => setP((v) => ({ ...v, bio: e.target.value }))}
            />
          </label>
          {msg && (
            <Alert kind={msg.kind} onClose={() => setMsg(null)}>
              {msg.text}
            </Alert>
          )}
          <PrimaryButton type="submit" loading={busy} className="w-full">
            Save profile
          </PrimaryButton>
        </form>
      </Card>
    </div>
  );
}
