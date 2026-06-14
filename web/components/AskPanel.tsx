"use client";

import { useState } from "react";
import { AskResponse, call } from "@/lib/api";
import { useSessionState } from "@/lib/session-state";
import { Alert, Badge, Card, PrimaryButton, Spinner } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { IconChat, IconCheck, IconCopy, IconX } from "@/components/icons";

type Entry = { q: string } & AskResponse;
type AskPanelState = { question: string; history: Entry[] };

const ASK_STATE_KEY = "docqa:ask-panel";

const MODE_TONE = {
  direct: "indigo",
  rag: "emerald",
  structured: "amber",
  decision: "emerald",
  memory: "indigo",
  none: "zinc",
} as const;

const MODE_HINT = {
  direct: "answered from the full text of your documents",
  rag: "answered from the most relevant passages",
  structured: "computed exactly with SQL over your tables",
  decision: "recommendations grounded in your uploaded evidence",
  memory: "answered from your saved memory",
  none: "",
} as const;

const SUGGESTIONS = [
  "Summarize the key points across all my files",
  "Which region generated the most revenue?",
  "What is the average score in the survey data?",
  "List any complaints or issues mentioned",
  "What should we prioritize next?",
];

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      onClick={copy}
      className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-faint transition hover:bg-inset hover:text-fg"
      aria-label="Copy answer"
    >
      {copied ? (
        <IconCheck className="h-3.5 w-3.5" />
      ) : (
        <IconCopy className="h-3.5 w-3.5" />
      )}
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function AskPanel({
  token,
  hasFiles,
  onAuthExpired,
  onAnswered,
}: {
  token: string;
  hasFiles: boolean;
  onAuthExpired: () => void;
  onAnswered?: () => void;
}) {
  const [panelState, setPanelState] = useSessionState<AskPanelState>(
    ASK_STATE_KEY,
    { question: "", history: [] },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { question, history } = panelState;
  const setQuestion = (next: string) =>
    setPanelState((current) => ({ ...current, question: next }));
  const setHistory = (next: Entry[] | ((current: Entry[]) => Entry[])) =>
    setPanelState((current) => ({
      ...current,
      history: typeof next === "function" ? next(current.history) : next,
    }));

  async function ask(e?: React.FormEvent, preset?: string) {
    e?.preventDefault();
    const q = (preset ?? question).trim();
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

    setPanelState((current) => ({
      ...current,
      question: "",
      history: [{ q, ...r.data! }, ...current.history],
    }));
    if (r.data.mode === "memory") onAnswered?.(); // refresh sidebar memory list
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
              : "Upload some documents first, then ask away"
          }
          className="w-full resize-none rounded-2xl border border-edge-strong bg-field px-4 py-3 text-sm text-fg placeholder-faint transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
        />
        <div className="flex items-center justify-between gap-3">
          <p className="hidden text-xs text-faint sm:block">
            Enter to send. Shift+Enter for a new line.
          </p>
          <PrimaryButton
            type="submit"
            loading={busy}
            disabled={!question.trim() || !hasFiles}
            className="w-full sm:w-auto"
          >
            {busy ? "Thinking..." : "Ask"}
          </PrimaryButton>
        </div>
      </form>

      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      {busy && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner /> Reading your documents...
        </Card>
      )}

      {history.length === 0 && !busy && (
        <div className="rounded-2xl border border-dashed border-edge px-4 py-8 text-center">
          <IconChat className="mx-auto h-7 w-7 text-faint" />
          <p className="mt-2 text-sm text-muted">
            Answers appear here, grounded in your files, with sources.
          </p>
          {hasFiles && (
            <div className="mx-auto mt-4 flex max-w-md flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(undefined, s)}
                  className="rounded-full border border-edge bg-panel px-3 py-1.5 text-xs text-muted transition hover:border-accent/50 hover:text-fg"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {history.length > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-xs font-medium uppercase tracking-wide text-faint">
            {history.length} answer{history.length === 1 ? "" : "s"} this
            session
          </p>
          <button
            onClick={() => setHistory([])}
            className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[11px] font-medium text-faint transition hover:bg-inset hover:text-fg"
          >
            <IconX className="h-3 w-3" /> Clear
          </button>
        </div>
      )}

      <div className="space-y-4">
        {history.map((entry, i) => (
          <Card key={history.length - i} className="overflow-hidden">
            <div className="flex items-center justify-between gap-2 border-b border-edge bg-inset/50 px-4 py-3">
              <p className="min-w-0 flex-1 text-sm font-medium text-fg">
                {entry.q}
              </p>
              <CopyButton text={entry.answer} />
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
                <p className="text-[11px] text-faint">
                  {MODE_HINT[entry.mode]}
                </p>
              )}
              {entry.sql && (
                <details className="group">
                  <summary className="cursor-pointer text-[11px] font-medium text-faint transition hover:text-muted">
                    Show the SQL used
                  </summary>
                  <pre className="mt-2 overflow-x-auto rounded-lg bg-[#161d2e] p-3 text-[11px] leading-relaxed text-emerald-300">
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
