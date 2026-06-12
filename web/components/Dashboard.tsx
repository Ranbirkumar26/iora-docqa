"use client";

import { useCallback, useEffect, useState } from "react";
import { call, FileRow, Memory, Status } from "@/lib/api";
import { Badge, Card, GhostButton } from "@/components/ui";
import { Wordmark } from "@/components/Brand";
import { IconTrash } from "@/components/icons";
import ThemeToggle from "@/components/ThemeToggle";
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
  const [memories, setMemories] = useState<Memory[]>([]);

  const refresh = useCallback(async () => {
    const [s, f, m] = await Promise.all([
      call<Status>("GET", "/status", { token }),
      call<{ files: FileRow[] }>("GET", "/files", { token }),
      call<{ memories: Memory[] }>("GET", "/memories", { token }),
    ]);
    if (s.status === 401 || f.status === 401) return onAuthExpired();
    if (s.data) setStatus(s.data);
    if (f.data) setFiles(f.data.files);
    if (m.data) setMemories(m.data.memories);
  }, [token, onAuthExpired]);

  async function deleteMemory(id: string) {
    await call("DELETE", `/memories/${id}`, { token });
    refresh();
  }

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
            <p className="text-[11px] uppercase tracking-wide text-faint">
              Files
            </p>
          </div>
          <div>
            <p className="text-xl font-bold">
              {status ? fmtTokens(status.total_tokens) : "-"}
            </p>
            <p className="text-[11px] uppercase tracking-wide text-faint">
              Tokens
            </p>
          </div>
          <div className="grid place-items-center">
            <Badge tone={status?.mode === "rag" ? "emerald" : "indigo"}>
              {status?.mode ?? "..."}
            </Badge>
            <p className="mt-1 text-[11px] uppercase tracking-wide text-faint">
              Mode
            </p>
          </div>
        </div>
      </Card>

      <UploadZone token={token} onDone={refresh} onAuthExpired={onAuthExpired} />

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Your files ({files.length})
        </h3>
        <FileList
          token={token}
          files={files}
          onChanged={refresh}
          onAuthExpired={onAuthExpired}
        />
      </div>

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Memory ({memories.length})
        </h3>
        {memories.length === 0 ? (
          <p className="rounded-xl border border-dashed border-edge px-3 py-4 text-center text-[11px] leading-relaxed text-faint">
            Type &quot;remember ...&quot; when you ask, e.g. &quot;remember my
            name is Ranbir&quot;. Saved facts are used to answer questions about
            you.
          </p>
        ) : (
          <ul className="space-y-1.5">
            {memories.map((m) => (
              <li
                key={m.id}
                className="flex items-center gap-2 rounded-xl border border-edge/80 bg-panel px-3 py-2"
              >
                <span className="min-w-0 flex-1 truncate text-sm text-fg">
                  {m.content}
                </span>
                <button
                  onClick={() => deleteMemory(m.id)}
                  className="grid min-h-8 min-w-8 shrink-0 place-items-center rounded-lg text-faint transition hover:bg-inset hover:text-red-400"
                  aria-label={`Forget: ${m.content}`}
                >
                  <IconTrash className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex min-h-dvh flex-col">
      {/* header */}
      <header className="sticky top-0 z-20 border-b border-edge bg-surface/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
          <div className="flex items-baseline gap-2.5">
            <Wordmark className="text-[26px]" />
            <span className="hidden text-[11px] font-semibold uppercase tracking-[0.18em] text-faint sm:block">
              DocQA
            </span>
          </div>
          <div className="flex items-center gap-2">
            {status && (
              <span className="hidden text-xs text-faint sm:block">
                {status.total_files} file{status.total_files === 1 ? "" : "s"} ·{" "}
                {fmtTokens(status.total_tokens)} tokens
              </span>
            )}
            <ThemeToggle />
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
            <nav className="mb-5 grid grid-cols-3 rounded-xl bg-inset p-1 lg:max-w-xs lg:grid-cols-2">
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
                      ? "bg-panel text-fg shadow"
                      : "text-muted hover:text-fg"
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
                  onAnswered={refresh}
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
                      onAnswered={refresh}
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
