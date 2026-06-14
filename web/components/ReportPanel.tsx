"use client";

import { useCallback, useEffect, useState } from "react";
import { call, JobRow, ReportResponse, ReportRow } from "@/lib/api";
import { useSessionState } from "@/lib/session-state";
import { Alert, Badge, Card, GhostButton, PrimaryButton, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { IconClipboard, IconDownload } from "@/components/icons";

function downloadMarkdown(text: string) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "iora-docqa-report.md";
  a.click();
  URL.revokeObjectURL(url);
}

const REPORT_STATE_KEY = "docqa:report-panel";

export default function ReportPanel({
  token,
  hasFiles,
  onAuthExpired,
}: {
  token: string;
  hasFiles: boolean;
  onAuthExpired: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useSessionState<ReportResponse | null>(
    REPORT_STATE_KEY,
    null,
  );
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [jobs, setJobs] = useState<JobRow[]>([]);

  const refreshHistory = useCallback(async () => {
    const [r, j] = await Promise.all([
      call<{ reports: ReportRow[] }>("GET", "/reports", { token }),
      call<{ jobs: JobRow[] }>("GET", "/jobs", { token }),
    ]);
    if (r.status === 401 || j.status === 401) return onAuthExpired();
    if (r.data) setReports(r.data.reports);
    if (j.data) setJobs(j.data.jobs);
  }, [token, onAuthExpired]);

  useEffect(() => {
    if (hasFiles) refreshHistory();
  }, [hasFiles, refreshHistory]);

  async function run() {
    setBusy(true);
    setError(null);
    const r = await call<ReportResponse>("POST", "/report", { token });
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Something went wrong");
    setResult(r.data);
    refreshHistory();
  }

  async function openReport(id: string) {
    setError(null);
    const r = await call<ReportResponse>("GET", `/reports/${id}`, { token });
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Could not open report");
    setResult(r.data);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Generate an executive report with statistical and qualitative signals.
        </p>
        <PrimaryButton
          onClick={run}
          loading={busy}
          disabled={!hasFiles}
          className="w-full sm:w-auto"
        >
          {busy ? "Generating..." : result ? "Regenerate" : "Generate report"}
        </PrimaryButton>
      </div>

      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      {jobs.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {jobs.slice(0, 3).map((job) => (
            <Badge
              key={job.id}
              tone={
                job.status === "failed"
                  ? "amber"
                  : job.status === "completed"
                    ? "emerald"
                    : "indigo"
              }
            >
              {job.kind.replace("_", " ")}: {job.status}
            </Badge>
          ))}
        </div>
      )}

      {busy && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner /> Analyzing tables, text, risks, and opportunities...
        </Card>
      )}

      {!result && !busy && (
        <div className="rounded-2xl border border-dashed border-edge px-4 py-10 text-center">
          <IconClipboard className="mx-auto h-7 w-7 text-faint" />
          <p className="mt-2 text-sm text-muted">
            {hasFiles
              ? "Turn the uploaded corpus into a structured decision report."
              : "Upload documents first, then generate a report."}
          </p>
        </div>
      )}

      {reports.length > 0 && !busy && (
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-faint">
            Saved reports
          </p>
          <ul className="space-y-1.5">
            {reports.slice(0, 5).map((report) => (
              <li
                key={report.id}
                className="flex items-center gap-2 rounded-xl border border-edge/80 bg-panel px-3 py-2"
              >
                <button
                  onClick={() => openReport(report.id)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate text-sm font-medium text-fg">
                    {report.title}
                  </span>
                  <span className="block text-[11px] text-faint">
                    {new Date(report.created_at).toLocaleString()} ·{" "}
                    {report.sources.length} sources
                  </span>
                </button>
                <Badge tone={report.mode === "rag" ? "emerald" : "indigo"}>
                  {report.mode}
                </Badge>
              </li>
            ))}
          </ul>
        </div>
      )}

      {result && !busy && (
        <Card className="space-y-4 p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5">
              <Badge tone={result.mode === "rag" ? "emerald" : "indigo"}>
                {result.mode}
              </Badge>
              <Badge>{result.sources.length} sources</Badge>
            </div>
            <GhostButton
              onClick={() => downloadMarkdown(result.report)}
              className="!min-h-9 !px-3 text-xs"
            >
              <IconDownload className="h-3.5 w-3.5" /> Download .md
            </GhostButton>
          </div>
          <Markdown>{result.report}</Markdown>

          <details className="group rounded-xl border border-edge bg-inset/40 px-3 py-2">
            <summary className="cursor-pointer text-xs font-medium text-muted transition hover:text-fg">
              Analysis inputs
            </summary>
            <div className="mt-3 space-y-4">
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">
                  Structured
                </p>
                <Markdown>{result.structured_analysis || "No structured analysis."}</Markdown>
              </div>
              <div>
                <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-faint">
                  Qualitative
                </p>
                <Markdown>{result.qualitative_analysis || "No qualitative analysis."}</Markdown>
              </div>
            </div>
          </details>
        </Card>
      )}
    </div>
  );
}
