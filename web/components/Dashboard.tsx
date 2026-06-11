"use client";

import { useCallback, useEffect, useState } from "react";
import { call, FileRow, Status } from "@/lib/api";
import { Badge, Card, GhostButton } from "@/components/ui";
import UploadZone from "@/components/UploadZone";
import FileList from "@/components/FileList";
import AskPanel from "@/components/AskPanel";
import SummarizePanel from "@/components/SummarizePanel";

type Tab = "ask" | "summarize" | "files";

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

export default function Dashboard({
  token,
  onLogout,
  onAuthExpired,
}: {
  token: string;
  onLogout: () => void;
  onAuthExpired: () => void;
}) {
  const [tab, setTab] = useState<Tab>("ask");
  const [status, setStatus] = useState<Status | null>(null);
  const [files, setFiles] = useState<FileRow[]>([]);

  const refresh = useCallback(async () => {
    const [s, f] = await Promise.all([
      call<Status>("GET", "/status", { token }),
      call<{ files: FileRow[] }>("GET", "/files", { token }),
    ]);
    if (s.status === 401 || f.status === 401) return onAuthExpired();
    if (s.data) setStatus(s.data);
    if (f.data) setFiles(f.data.files);
  }, [token, onAuthExpired]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasFiles = files.length > 0;

  const corpusPanel = (
    <div className="space-y-5">
      {/* stats */}
      <Card className="p-4">
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-xl font-bold">{status?.total_files ?? "-"}</p>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              Files
            </p>
          </div>
          <div>
            <p className="text-xl font-bold">
              {status ? fmtTokens(status.total_tokens) : "-"}
            </p>
            <p className="text-[11px] uppercase tracking-wide text-zinc-500">
              Tokens
            </p>
          </div>
          <div className="grid place-items-center">
            <Badge tone={status?.mode === "rag" ? "emerald" : "indigo"}>
              {status?.mode ?? "..."}
            </Badge>
            <p className="mt-1 text-[11px] uppercase tracking-wide text-zinc-500">
              Mode
            </p>
          </div>
        </div>
      </Card>

      <UploadZone token={token} onDone={refresh} onAuthExpired={onAuthExpired} />

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Your files ({files.length})
        </h3>
        <FileList
          token={token}
          files={files}
          onChanged={refresh}
          onAuthExpired={onAuthExpired}
        />
      </div>
    </div>
  );

  return (
    <div className="flex min-h-dvh flex-col">
      {/* header */}
      <header className="sticky top-0 z-20 border-b border-zinc-800/80 bg-zinc-950/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
          <div className="flex items-center gap-2.5">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icon.svg" alt="" className="h-8 w-8 rounded-lg" />
            <span className="text-base font-bold tracking-tight">DocQA</span>
          </div>
          <div className="flex items-center gap-2">
            {status && (
              <span className="hidden text-xs text-zinc-500 sm:block">
                {status.total_files} file{status.total_files === 1 ? "" : "s"} ·{" "}
                {fmtTokens(status.total_tokens)} tokens
              </span>
            )}
            <GhostButton onClick={onLogout} className="!min-h-9 !px-3 text-xs">
              Log out
            </GhostButton>
          </div>
        </div>
      </header>

      {/* body */}
      <div className="mx-auto w-full max-w-6xl flex-1 px-4 py-5 lg:py-8">
        <div className="lg:grid lg:grid-cols-[340px_1fr] lg:gap-8">
          {/* desktop sidebar */}
          <aside className="hidden lg:block">{corpusPanel}</aside>

          {/* main column */}
          <main className="min-w-0">
            {/* tab bar; Files tab only exists on mobile */}
            <nav className="mb-5 grid grid-cols-3 rounded-xl bg-zinc-900 p-1 lg:max-w-xs lg:grid-cols-2">
              {(
                [
                  ["ask", "Ask"],
                  ["summarize", "Summarize"],
                  ["files", `Files (${files.length})`],
                ] as [Tab, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`min-h-10 rounded-lg text-sm font-medium transition ${
                    key === "files" ? "lg:hidden" : ""
                  } ${
                    tab === key
                      ? "bg-zinc-950 text-white shadow"
                      : "text-zinc-400 hover:text-zinc-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>

            <div className="safe-bottom">
              {tab === "ask" && (
                <AskPanel
                  token={token}
                  hasFiles={hasFiles}
                  onAuthExpired={onAuthExpired}
                />
              )}
              {tab === "summarize" && (
                <SummarizePanel
                  token={token}
                  hasFiles={hasFiles}
                  onAuthExpired={onAuthExpired}
                />
              )}
              {/* mobile-only corpus tab; on desktop the sidebar always shows it,
                  so fall back to Ask if the viewport grows past lg */}
              {tab === "files" && (
                <>
                  <div className="lg:hidden">{corpusPanel}</div>
                  <div className="hidden lg:block">
                    <AskPanel
                      token={token}
                      hasFiles={hasFiles}
                      onAuthExpired={onAuthExpired}
                    />
                  </div>
                </>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
