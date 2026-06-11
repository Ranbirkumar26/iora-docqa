"use client";

import { useState } from "react";
import { AskResponse, call } from "@/lib/api";
import { Alert, Badge, Card, PrimaryButton, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";

type Entry = { q: string } & AskResponse;

const MODE_TONE = {
  direct: "indigo",
  rag: "emerald",
  structured: "amber",
  none: "zinc",
} as const;

const MODE_HINT = {
  direct: "answered from the full text of your documents",
  rag: "answered from the most relevant passages",
  structured: "computed exactly with SQL over your tables",
  none: "",
} as const;

export default function AskPanel({
  token,
  hasFiles,
  onAuthExpired,
}: {
  token: string;
  hasFiles: boolean;
  onAuthExpired: () => void;
}) {
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<Entry[]>([]);

  async function ask(e?: React.FormEvent) {
    e?.preventDefault();
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);

    const r = await call<AskResponse>("POST", "/ask", {
      token,
      json: { question: q },
    });
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Something went wrong");

    setHistory((h) => [{ q, ...r.data! }, ...h]);
    setQuestion("");
  }

  return (
    <div className="space-y-4">
      <form onSubmit={ask} className="space-y-3">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              ask();
            }
          }}
          rows={3}
          placeholder={
            hasFiles
              ? "e.g. Which region generated the most revenue?"
              : "Upload some documents first, then ask away…"
          }
          className="w-full resize-none rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/30"
        />
        <div className="flex items-center justify-between gap-3">
          <p className="hidden text-xs text-zinc-500 sm:block">
            Enter to send · Shift+Enter for a new line
          </p>
          <PrimaryButton
            type="submit"
            loading={busy}
            disabled={!question.trim() || !hasFiles}
            className="w-full sm:w-auto"
          >
            {busy ? "Thinking…" : "Ask"}
          </PrimaryButton>
        </div>
      </form>

      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      {busy && (
        <Card className="flex items-center gap-3 p-4 text-sm text-zinc-400">
          <Spinner /> Reading your documents…
        </Card>
      )}

      {history.length === 0 && !busy && (
        <div className="rounded-2xl border border-dashed border-zinc-800 px-4 py-10 text-center">
          <p className="text-3xl">💬</p>
          <p className="mt-2 text-sm text-zinc-400">
            Answers appear here — grounded in your files, with sources.
          </p>
        </div>
      )}

      <div className="space-y-4">
        {history.map((entry, i) => (
          <Card key={history.length - i} className="overflow-hidden">
            <div className="border-b border-zinc-800 bg-zinc-900/80 px-4 py-3">
              <p className="text-sm font-medium text-zinc-100">{entry.q}</p>
            </div>
            <div className="space-y-3 px-4 py-4">
              <Markdown>{entry.answer}</Markdown>
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <Badge tone={MODE_TONE[entry.mode]}>{entry.mode}</Badge>
                {entry.sources?.map((s) => (
                  <Badge key={s}>{s}</Badge>
                ))}
              </div>
              {MODE_HINT[entry.mode] && (
                <p className="text-[11px] text-zinc-500">
                  {MODE_HINT[entry.mode]}
                </p>
              )}
              {entry.sql && (
                <details className="group">
                  <summary className="cursor-pointer text-[11px] font-medium text-zinc-500 transition hover:text-zinc-300">
                    Show the SQL used
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-zinc-950 p-3 text-[11px] leading-relaxed text-emerald-300">
                    {entry.sql}
                  </pre>
                </details>
              )}
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
