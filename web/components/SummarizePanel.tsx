"use client";

import { useState } from "react";
import { call, SummarizeResponse } from "@/lib/api";
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

export default function SummarizePanel({
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
  const [result, setResult] = useState<SummarizeResponse | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    const r = await call<SummarizeResponse>("POST", "/summarize", { token });
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Something went wrong");
    setResult(r.data);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-muted">
          Get a summary of every file, plus one overall picture.
        </p>
        <PrimaryButton
          onClick={run}
          loading={busy}
          disabled={!hasFiles}
          className="w-full sm:w-auto"
        >
          {busy ? "Summarizing..." : result ? "Regenerate" : "Generate summary"}
        </PrimaryButton>
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
              ? "One tap and every document gets summarized."
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
