"use client";

import { useCallback, useEffect, useState } from "react";
import { call, GeneratedOutput, SummarizeResponse } from "@/lib/api";
import { useSessionState } from "@/lib/session-state";
import { Alert, Badge, Card, GhostButton, PrimaryButton, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { IconClipboard, IconDownload } from "@/components/icons";

function downloadMarkdown(text: string) {
  const blob = new Blob([text], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "iora-docqa-summary.md";
  a.click();
  URL.revokeObjectURL(url);
}

const SUMMARY_STATE_KEY = "docqa:summarize-panel";

function outputToSummary(output: GeneratedOutput): SummarizeResponse {
  const mode =
    output.metadata?.mode === "rag" || output.metadata?.mode === "direct"
      ? output.metadata.mode
      : "direct";
  return {
    summary: output.content,
    mode,
    collective: output.kind === "collective_summary",
  };
}

export default function SummarizePanel({
  token,
  hasFiles,
  readOnly = false,
  onAuthExpired,
  onGenerated,
}: {
  token: string;
  hasFiles: boolean;
  readOnly?: boolean;
  onAuthExpired: () => void;
  onGenerated?: () => void;
}) {
  const [busy, setBusy] = useState<"individual" | "collective" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useSessionState<SummarizeResponse | null>(
    SUMMARY_STATE_KEY,
    null,
  );

  const loadSaved = useCallback(async () => {
    const r = await call<{ outputs: GeneratedOutput[] }>(
      "GET",
      "/outputs?kind=summary_batch,collective_summary",
      { token },
    );
    if (r.status === 401) return onAuthExpired();
    if (r.data?.outputs.length) setResult(outputToSummary(r.data.outputs[0]));
  }, [token, onAuthExpired, setResult]);

  useEffect(() => {
    if (hasFiles) loadSaved();
  }, [hasFiles, loadSaved]);

  async function run(collective = false) {
    if (readOnly) return;
    setBusy(collective ? "collective" : "individual");
    setError(null);
    const r = await call<SummarizeResponse>("POST", "/summarize", {
      token,
      json: { collective },
    });
    setBusy(null);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Something went wrong");
    setResult(r.data);
    onGenerated?.();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          {readOnly
            ? "Read-only mode can view saved summaries. Use Ask for collective analysis."
            : "Keep per-file summaries separate. Combine them only when you ask."}
        </p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <PrimaryButton
            onClick={() => run(false)}
            loading={busy === "individual"}
            disabled={!hasFiles || !!busy || readOnly}
            className="w-full sm:w-auto"
          >
            {busy === "individual" ? "Summarizing..." : "Individual summaries"}
          </PrimaryButton>
          <GhostButton
            onClick={() => run(true)}
            disabled={!hasFiles || !!busy || readOnly}
            className="w-full sm:w-auto"
          >
            {busy === "collective" ? "Combining..." : "Collective summary"}
          </GhostButton>
        </div>
      </div>

      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      {busy && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner /> Reading every document. This can take a moment...
        </Card>
      )}

      {!result && !busy && (
        <div className="rounded-2xl border border-dashed border-edge px-4 py-10 text-center">
          <IconClipboard className="mx-auto h-7 w-7 text-faint" />
          <p className="mt-2 text-sm text-muted">
            {hasFiles
              ? readOnly
                ? "No saved summaries are available in this workspace yet."
                : "One tap and every document gets summarized."
              : "Upload documents first, then summarize them all at once."}
          </p>
        </div>
      )}

      {result && !busy && (
        <Card className="space-y-3 p-4 sm:p-5">
          <div className="flex items-center justify-between gap-2">
            <Badge tone={result.mode === "rag" ? "emerald" : "indigo"}>
              {result.mode}
            </Badge>
            <GhostButton
              onClick={() => downloadMarkdown(result.summary)}
              className="!min-h-9 !px-3 text-xs"
            >
              <IconDownload className="h-3.5 w-3.5" /> Download .md
            </GhostButton>
          </div>
          <Markdown>{result.summary}</Markdown>
        </Card>
      )}
    </div>
  );
}
