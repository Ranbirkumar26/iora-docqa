"use client";

import { useState } from "react";
import { call, SummarizeResponse } from "@/lib/api";
import { Alert, Badge, Card, PrimaryButton, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { IconClipboard } from "@/components/icons";

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
        <p className="text-sm text-zinc-400">
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
        <Card className="flex items-center gap-3 p-4 text-sm text-zinc-400">
          <Spinner /> Reading every document. This can take a moment...
        </Card>
      )}

      {!result && !busy && (
        <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-10 text-center">
          <IconClipboard className="mx-auto h-7 w-7 text-zinc-600" />
          <p className="mt-2 text-sm text-zinc-400">
            {hasFiles
              ? "One tap and every document gets summarized."
              : "Upload documents first, then summarize them all at once."}
          </p>
        </div>
      )}

      {result && !busy && (
        <Card className="space-y-3 p-4 sm:p-5">
          <Badge tone={result.mode === "rag" ? "emerald" : "indigo"}>
            {result.mode}
          </Badge>
          <Markdown>{result.summary}</Markdown>
        </Card>
      )}
    </div>
  );
}
