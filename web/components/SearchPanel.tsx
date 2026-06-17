"use client";

import { useState } from "react";
import { call, SearchResponse, SearchResult } from "@/lib/api";
import { useSessionState } from "@/lib/session-state";
import { Alert, Badge, Card, PrimaryButton } from "@/components/ui";
import Markdown from "@/components/Markdown";
import { IconSearch } from "@/components/icons";

type SearchPanelState = { query: string; results: SearchResult[]; ran: boolean };

const SEARCH_STATE_KEY = "docqa:search-panel";

export default function SearchPanel({
  token,
  hasFiles,
  onAuthExpired,
}: {
  token: string;
  hasFiles: boolean;
  onAuthExpired: () => void;
}) {
  const [panelState, setPanelState] = useSessionState<SearchPanelState>(
    SEARCH_STATE_KEY,
    { query: "", results: [], ran: false },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { query, results, ran } = panelState;

  async function search(e?: React.FormEvent) {
    e?.preventDefault();
    const q = query.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);

    const r = await call<SearchResponse>(
      "GET",
      `/search?q=${encodeURIComponent(q)}`,
      { token },
    );
    setBusy(false);
    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) return setError(r.error ?? "Search failed");

    setPanelState((current) => ({
      ...current,
      results: r.data!.results,
      ran: true,
    }));
  }

  return (
    <div className="space-y-4">
      <form onSubmit={search} className="space-y-3">
        <div className="relative">
          <IconSearch className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-faint" />
          <input
            value={query}
            onChange={(e) =>
              setPanelState((current) => ({ ...current, query: e.target.value }))
            }
            placeholder={
              hasFiles
                ? "Keyword search, e.g. invoice 2023 or refund"
                : "Upload some documents first, then search"
            }
            className="min-h-11 w-full rounded-2xl border border-edge-strong bg-field py-2.5 pl-10 pr-4 text-sm text-fg placeholder-faint transition focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30"
          />
        </div>
        <div className="flex items-center justify-between gap-3">
          <p className="hidden text-xs text-faint sm:block">
            Exact keyword match across your files. Quote &quot;a phrase&quot;, or
            use OR to widen.
          </p>
          <PrimaryButton
            type="submit"
            loading={busy}
            disabled={!query.trim() || !hasFiles}
            className="w-full sm:w-auto"
          >
            {busy ? "Searching..." : "Search"}
          </PrimaryButton>
        </div>
      </form>

      {error && <Alert onClose={() => setError(null)}>{error}</Alert>}

      {ran && !busy && results.length === 0 && (
        <div className="rounded-2xl border border-dashed border-edge px-4 py-8 text-center">
          <IconSearch className="mx-auto h-7 w-7 text-faint" />
          <p className="mt-2 text-sm text-muted">
            No passages matched that search.
          </p>
        </div>
      )}

      {results.length > 0 && (
        <>
          <p className="text-xs font-medium uppercase tracking-wide text-faint">
            {results.length} passage{results.length === 1 ? "" : "s"}
          </p>
          <div className="space-y-3">
            {results.map((r, i) => (
              <Card key={`${r.filename}-${i}`} className="overflow-hidden">
                <div className="flex items-center justify-between gap-2 border-b border-edge bg-inset/50 px-4 py-2.5">
                  <Badge>{r.filename}</Badge>
                </div>
                <div className="px-4 py-3 text-sm text-muted">
                  <Markdown>{r.snippet || r.content.slice(0, 280)}</Markdown>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
