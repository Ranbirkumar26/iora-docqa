"use client";

import { useCallback, useEffect, useState } from "react";
import {
  call,
  AuditEvent,
  ConversationExport,
  FileRow,
  GeneratedOutput,
  MemberRow,
  Memory,
  Status,
} from "@/lib/api";
import { Alert, Badge, Card, GhostButton } from "@/components/ui";
import { Wordmark } from "@/components/Brand";
import { IconDownload, IconTrash } from "@/components/icons";
import ThemeToggle from "@/components/ThemeToggle";
import UploadZone from "@/components/UploadZone";
import FileList from "@/components/FileList";
import AskPanel from "@/components/AskPanel";
import SearchPanel from "@/components/SearchPanel";
import SummarizePanel from "@/components/SummarizePanel";
import ReportPanel from "@/components/ReportPanel";
import SecurityPanel from "@/components/SecurityPanel";

type Tab = "ask" | "search" | "summarize" | "report" | "files";

function fmtTokens(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return `${n}`;
}

const ROLE_TONE = {
  user: "zinc",
  author: "amber",
  admin: "emerald",
} as const;

function downloadText(filename: string, mimeType: string, content: string) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export default function Dashboard({
  token,
  refreshToken,
  onLogout,
  onAuthExpired,
}: {
  token: string;
  refreshToken: string;
  onLogout: () => void;
  onAuthExpired: () => void;
}) {
  const [tab, setTab] = useState<Tab>("ask");
  const [status, setStatus] = useState<Status | null>(null);
  const [files, setFiles] = useState<FileRow[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [members, setMembers] = useState<MemberRow[]>([]);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [extractions, setExtractions] = useState<GeneratedOutput[]>([]);
  const [attachExport, setAttachExport] = useState(false);
  const [exportBusy, setExportBusy] = useState<"markdown" | "txt" | null>(null);
  const [exportMessage, setExportMessage] = useState<{
    kind: "ok" | "error";
    text: string;
  } | null>(null);
  const [accessMessage, setAccessMessage] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [s, f, m, o] = await Promise.all([
      call<Status>("GET", "/status", { token }),
      call<{ files: FileRow[] }>("GET", "/files", { token }),
      call<{ memories: Memory[] }>("GET", "/memories", { token }),
      call<{ outputs: GeneratedOutput[] }>("GET", "/outputs?kind=extraction", {
        token,
      }),
    ]);
    if (s.status === 401 || f.status === 401 || o.status === 401) {
      return onAuthExpired();
    }
    if (s.data) {
      setStatus(s.data);
      if (s.data.can_write_all) {
        const [membersRes, auditRes] = await Promise.all([
          call<{ members: MemberRow[] }>("GET", "/members", { token }),
          call<{ events: AuditEvent[] }>("GET", "/audit", { token }),
        ]);
        if (membersRes.status === 401 || auditRes.status === 401) {
          return onAuthExpired();
        }
        if (membersRes.data) setMembers(membersRes.data.members);
        if (auditRes.data) setAudit(auditRes.data.events);
      } else {
        setMembers([]);
        setAudit([]);
      }
    }
    if (f.data) setFiles(f.data.files);
    if (m.data) setMemories(m.data.memories);
    if (o.data) setExtractions(o.data.outputs);
  }, [token, onAuthExpired]);

  async function deleteMemory(id: string) {
    if (status?.is_read_only) return;
    await call("DELETE", `/memories/${id}`, { token });
    refresh();
  }

  async function updateMemberRole(userId: string, role: MemberRow["role"]) {
    setAccessMessage(null);
    const r = await call<{ member: MemberRow }>("PATCH", `/members/${userId}`, {
      token,
      json: { role },
    });
    if (r.status === 401) return onAuthExpired();
    if (r.error) {
      setAccessMessage(r.error);
      return;
    }
    refresh();
  }

  async function toggleSuspend(member: MemberRow) {
    setAccessMessage(null);
    const path = member.banned
      ? `/members/${member.user_id}/unsuspend`
      : `/members/${member.user_id}/suspend`;
    const r = await call("POST", path, { token });
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setAccessMessage(r.error);
    refresh();
  }

  async function removeMember(member: MemberRow) {
    const who = member.email || member.user_id;
    if (
      !window.confirm(
        `Remove ${who}? This permanently deletes their account and all their data.`,
      )
    )
      return;
    setAccessMessage(null);
    const r = await call("DELETE", `/members/${member.user_id}`, { token });
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setAccessMessage(r.error);
    refresh();
  }

  async function resetMfa(member: MemberRow) {
    const who = member.email || member.user_id;
    if (
      !window.confirm(
        `Reset 2FA for ${who}? They'll sign in with just their password until they re-enable it.`,
      )
    )
      return;
    setAccessMessage(null);
    const r = await call<{ ok: boolean; removed: number }>(
      "POST",
      `/members/${member.user_id}/mfa-reset`,
      { token },
    );
    if (r.status === 401) return onAuthExpired();
    if (r.error) return setAccessMessage(r.error);
    setAccessMessage(`2FA reset (${r.data?.removed ?? 0} factor(s) removed).`);
    refresh();
  }

  async function exportConversation(format: "markdown" | "txt") {
    setExportBusy(format);
    setExportMessage(null);
    const r = await call<ConversationExport>("POST", "/conversation/export", {
      token,
      json: { format, attach: canUpload && attachExport },
    });
    setExportBusy(null);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) {
      setExportMessage({ kind: "error", text: r.error ?? "Export failed" });
      return;
    }
    downloadText(r.data.filename, r.data.mime_type, r.data.content);
    setExportMessage({
      kind: "ok",
      text: r.data.attached
        ? "Export downloaded and added to the document repository."
        : "Export downloaded.",
    });
    refresh();
  }

  async function downloadOutput(output: GeneratedOutput) {
    const res = await fetch(`/api/outputs/${output.id}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 401) return onAuthExpired();
    if (!res.ok) return;
    const blob = await res.blob();
    const filename =
      typeof output.metadata?.download_filename === "string"
        ? output.metadata.download_filename
        : `${output.title}.txt`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    refresh();
  }, [refresh]);

  const hasFiles = files.length > 0;
  const canUpload = status?.can_upload !== false;
  const canDelete = status?.can_delete !== false;
  const canManageRoles = status?.can_write_all === true;
  const isReadOnly = status?.is_read_only === true;

  useEffect(() => {
    if (!canUpload && attachExport) setAttachExport(false);
  }, [attachExport, canUpload]);

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
        {status?.role && (
          <div className="mt-4 flex items-center justify-between gap-2 border-t border-edge pt-3">
            <span className="text-[11px] font-semibold uppercase tracking-wide text-faint">
              Access mode
            </span>
            <Badge tone={ROLE_TONE[status.role]}>{status.role}</Badge>
          </div>
        )}
        <div className="mt-4 grid grid-cols-2 gap-2 border-t border-edge pt-3 text-center">
          <div>
            <p className="text-lg font-bold">{status?.processed_documents ?? 0}</p>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              Processed
            </p>
          </div>
          <div>
            <p className="text-lg font-bold">{status?.available_reports ?? 0}</p>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              Reports
            </p>
          </div>
          <div>
            <p className="text-lg font-bold">{status?.available_summaries ?? 0}</p>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              Summaries
            </p>
          </div>
          <div>
            <p className="text-lg font-bold">
              {status?.exported_conversations ?? 0}
            </p>
            <p className="text-[10px] uppercase tracking-wide text-faint">
              Exports
            </p>
          </div>
        </div>
      </Card>

      {canUpload ? (
        <UploadZone token={token} onDone={refresh} onAuthExpired={onAuthExpired} />
      ) : (
        <Alert kind="warn">
          Author mode is read-only. You can view and ask questions over your own saved data,
          but uploads and deletes are disabled.
        </Alert>
      )}

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Your files ({files.length})
        </h3>
        <FileList
          token={token}
          files={files}
          canDelete={canDelete}
          onChanged={refresh}
          onAuthExpired={onAuthExpired}
        />
      </div>

      {extractions.length > 0 && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
            Extracted details ({extractions.length})
          </h3>
          <ul className="space-y-1.5">
            {extractions.slice(0, 5).map((output) => (
              <li
                key={output.id}
                className="flex items-center gap-2 rounded-xl border border-edge/80 bg-panel px-3 py-2"
              >
                <span className="min-w-0 flex-1 truncate text-sm text-fg">
                  {output.title.replace("Extracted details: ", "")}
                </span>
                <button
                  onClick={() => downloadOutput(output)}
                  className="grid min-h-8 min-w-8 shrink-0 place-items-center rounded-lg text-faint transition hover:bg-inset hover:text-fg"
                  aria-label={`Download ${output.title}`}
                >
                  <IconDownload className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
          Conversation export
        </h3>
        <Card className="space-y-3 p-3">
          <label className="flex items-start gap-2 text-xs text-muted">
            <input
              type="checkbox"
              checked={canUpload && attachExport}
              disabled={!canUpload}
              onChange={(e) => setAttachExport(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-edge text-accent"
            />
            <span>
              {canUpload
                ? "Add exported conversation to the document repository"
                : "Attach is disabled in read-only mode"}
            </span>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <GhostButton
              onClick={() => exportConversation("markdown")}
              disabled={!!exportBusy}
              className="!min-h-9 !px-3 text-xs"
            >
              {exportBusy === "markdown" ? "Exporting..." : "Export .md"}
            </GhostButton>
            <GhostButton
              onClick={() => exportConversation("txt")}
              disabled={!!exportBusy}
              className="!min-h-9 !px-3 text-xs"
            >
              {exportBusy === "txt" ? "Exporting..." : "Export .txt"}
            </GhostButton>
          </div>
        </Card>
        {exportMessage && (
          <div className="mt-2">
            <Alert
              kind={exportMessage.kind}
              onClose={() => setExportMessage(null)}
            >
              {exportMessage.text}
            </Alert>
          </div>
        )}
      </div>

      {canManageRoles && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
            Access control ({members.length})
          </h3>
          <Card className="space-y-2 p-3">
            {members.length === 0 ? (
              <p className="text-xs text-faint">No organisation members found.</p>
            ) : (
              members.map((member) => {
                const isSelf = member.user_id === status?.user_id;
                return (
                  <div
                    key={member.user_id}
                    className="space-y-1.5 rounded-lg border border-edge/70 bg-inset px-2.5 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate text-xs text-muted">
                        {member.email || member.user_id}
                        {isSelf ? " (you)" : ""}
                      </span>
                      {member.banned && (
                        <span className="shrink-0 rounded bg-red-500/15 px-1.5 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400">
                          suspended
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <select
                        value={member.role}
                        onChange={(e) =>
                          updateMemberRole(
                            member.user_id,
                            e.target.value as MemberRow["role"],
                          )
                        }
                        disabled={member.is_bootstrap_admin}
                        className="min-h-8 flex-1 rounded-lg border border-edge-strong bg-field px-2 text-xs text-fg focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
                        aria-label={`Role for ${member.email || member.user_id}`}
                      >
                        {member.is_bootstrap_admin ? (
                          <option value="admin">Admin</option>
                        ) : (
                          <>
                            <option value="user">User</option>
                            <option value="author">Author</option>
                            <option value="admin">Admin</option>
                          </>
                        )}
                      </select>
                      {!member.is_bootstrap_admin && !isSelf && (
                        <>
                          <button
                            onClick={() => toggleSuspend(member)}
                            className="min-h-8 shrink-0 rounded-lg border border-edge-strong px-2 text-[11px] text-muted transition hover:text-fg"
                          >
                            {member.banned ? "Reinstate" : "Suspend"}
                          </button>
                          <button
                            onClick={() => resetMfa(member)}
                            className="min-h-8 shrink-0 rounded-lg border border-edge-strong px-2 text-[11px] text-muted transition hover:text-fg"
                          >
                            Reset 2FA
                          </button>
                          <button
                            onClick={() => removeMember(member)}
                            aria-label={`Remove ${member.email || member.user_id}`}
                            className="grid min-h-8 min-w-8 shrink-0 place-items-center rounded-lg text-faint transition hover:bg-red-500/10 hover:text-red-500"
                          >
                            <IconTrash className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </Card>
          {accessMessage && (
            <div className="mt-2">
              <Alert onClose={() => setAccessMessage(null)}>{accessMessage}</Alert>
            </div>
          )}
        </div>
      )}

      {canManageRoles && (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
            Audit log ({audit.length})
          </h3>
          <Card className="max-h-64 space-y-2 overflow-y-auto p-3">
            {audit.length === 0 ? (
              <p className="text-xs text-faint">No recorded admin actions yet.</p>
            ) : (
              audit.map((e) => (
                <div key={e.id} className="text-[11px] leading-snug text-muted">
                  <span className="font-semibold text-fg">{e.action}</span>
                  {e.detail ? ` · ${e.detail}` : ""}
                  {e.target_user_id ? ` · ${e.target_user_id.slice(0, 8)}` : ""}
                  <span className="block text-faint">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </div>
              ))
            )}
          </Card>
        </div>
      )}

      <SecurityPanel
        token={token}
        refreshToken={refreshToken}
        onAuthExpired={onAuthExpired}
        onAccountDeleted={onLogout}
      />

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
                {!isReadOnly && (
                  <button
                    onClick={() => deleteMemory(m.id)}
                    className="grid min-h-8 min-w-8 shrink-0 place-items-center rounded-lg text-faint transition hover:bg-inset hover:text-red-400"
                    aria-label={`Forget: ${m.content}`}
                  >
                    <IconTrash className="h-3.5 w-3.5" />
                  </button>
                )}
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
                {status.organization_name ? `${status.organization_name} · ` : ""}
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
            <nav className="mb-5 grid grid-cols-5 rounded-xl bg-inset p-1 lg:max-w-xl lg:grid-cols-4">
              {(
                [
                  ["ask", "Ask"],
                  ["search", "Search"],
                  ["summarize", "Summarize"],
                  ["report", "Report"],
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
                  readOnly={isReadOnly}
                  onAuthExpired={onAuthExpired}
                  onAnswered={refresh}
                />
              )}
              {tab === "search" && (
                <SearchPanel
                  token={token}
                  hasFiles={hasFiles}
                  onAuthExpired={onAuthExpired}
                />
              )}
              {tab === "summarize" && (
                <SummarizePanel
                  token={token}
                  hasFiles={hasFiles}
                  readOnly={isReadOnly}
                  onAuthExpired={onAuthExpired}
                  onGenerated={refresh}
                />
              )}
              {tab === "report" && (
                <ReportPanel
                  token={token}
                  hasFiles={hasFiles}
                  readOnly={isReadOnly}
                  onAuthExpired={onAuthExpired}
                  onGenerated={refresh}
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
                      readOnly={isReadOnly}
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
