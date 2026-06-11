"use client";

import { useState } from "react";
import { call, FileRow } from "@/lib/api";
import { IconFileText, IconGrid, IconTable, IconTrash } from "@/components/icons";

function TypeIcon({ type }: { type: string }) {
  const cls = "h-4.5 w-4.5 shrink-0 text-zinc-400";
  if (type === "csv") return <IconTable className={cls} />;
  if (type === "xlsx") return <IconGrid className={cls} />;
  return <IconFileText className={cls} />;
}

function fmtChars(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M chars`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k chars`;
  return `${n} chars`;
}

export default function FileList({
  token,
  files,
  onChanged,
  onAuthExpired,
}: {
  token: string;
  files: FileRow[];
  onChanged: () => void;
  onAuthExpired: () => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function remove(id: string) {
    setDeleting(id);
    const r = await call("DELETE", `/files/${id}`, { token });
    setDeleting(null);
    setConfirming(null);
    if (r.status === 401) return onAuthExpired();
    onChanged();
  }

  if (!files.length) {
    return (
      <p className="rounded-xl border border-dashed border-zinc-800 px-3 py-6 text-center text-xs text-zinc-500">
        No files yet. Upload some to get started.
      </p>
    );
  }

  return (
    <ul className="space-y-1.5">
      {files.map((f) => (
        <li
          key={f.id}
          className="group flex items-center gap-2.5 rounded-xl border border-zinc-800/80 bg-zinc-900/40 px-3 py-2.5"
        >
          <TypeIcon type={f.file_type} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-zinc-200">{f.filename}</p>
            <p className="text-[11px] text-zinc-500">
              {fmtChars(f.char_count)}
              {" · "}
              {new Date(f.upload_date).toLocaleDateString()}
              {!f.indexed && " · indexing..."}
            </p>
          </div>
          {confirming === f.id ? (
            <div className="flex shrink-0 items-center gap-1">
              <button
                onClick={() => remove(f.id)}
                disabled={deleting === f.id}
                className="min-h-9 rounded-lg bg-red-500/15 px-2.5 text-xs font-semibold text-red-300 transition hover:bg-red-500/25 disabled:opacity-50"
              >
                {deleting === f.id ? "…" : "Delete"}
              </button>
              <button
                onClick={() => setConfirming(null)}
                className="min-h-9 rounded-lg px-2 text-xs text-zinc-400 transition hover:text-zinc-200"
              >
                Keep
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirming(f.id)}
              className="grid min-h-9 min-w-9 shrink-0 place-items-center rounded-lg text-zinc-500 transition hover:bg-zinc-800 hover:text-red-400"
              aria-label={`Delete ${f.filename}`}
            >
              <IconTrash className="h-4 w-4" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
