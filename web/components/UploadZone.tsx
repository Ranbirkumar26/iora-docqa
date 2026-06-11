"use client";

import { useRef, useState } from "react";
import { call, UploadResponse } from "@/lib/api";
import { Alert, PrimaryButton } from "@/components/ui";
import { IconUpload, IconX } from "@/components/icons";

const ACCEPT = ".txt,.csv,.xlsx";

export default function UploadZone({
  token,
  onDone,
  onAuthExpired,
}: {
  token: string;
  onDone: () => void;
  onAuthExpired: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [queued, setQueued] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [messages, setMessages] = useState<
    { kind: "ok" | "warn" | "error"; text: string }[]
  >([]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    setQueued((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...Array.from(list).filter((f) => !names.has(f.name))];
    });
    setMessages([]);
  }

  async function upload() {
    if (!queued.length) return;
    setBusy(true);
    setMessages([]);

    const form = new FormData();
    queued.forEach((f) => form.append("files", f));

    const r = await call<UploadResponse>("POST", "/upload", { token, form });
    setBusy(false);

    if (r.status === 401) return onAuthExpired();
    if (r.error || !r.data) {
      setMessages([{ kind: "error", text: r.error ?? "Upload failed" }]);
      return;
    }

    const msgs: { kind: "ok" | "warn" | "error"; text: string }[] = [];
    const added = r.data.uploaded.length;
    const replaced = r.data.replaced.length;
    if (added || replaced) {
      msgs.push({
        kind: "ok",
        text:
          `Added ${added} file${added === 1 ? "" : "s"}` +
          (replaced ? `, replaced ${replaced}` : "") +
          ".",
      });
    }
    r.data.skipped.forEach((s) =>
      msgs.push({ kind: "warn", text: `${s.filename}: ${s.reason}` }),
    );
    setMessages(msgs);
    setQueued([]);
    onDone();
  }

  return (
    <div className="space-y-3">
      {/* drop target / picker */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          addFiles(e.dataTransfer.files);
        }}
        className={`w-full rounded-2xl border-2 border-dashed px-4 py-7 text-center transition ${
          drag
            ? "border-accent bg-accent/10"
            : "border-edge-strong bg-inset/40 hover:border-accent/60"
        }`}
      >
        <IconUpload className="mx-auto h-6 w-6 text-muted" />
        <p className="mt-2 text-sm font-medium text-fg">
          Tap to choose files
          <span className="hidden sm:inline"> or drag &amp; drop</span>
        </p>
        <p className="mt-1 text-xs text-faint">
          .txt, .csv, .xlsx (up to 100 files, 10MB each)
        </p>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          addFiles(e.target.files);
          e.target.value = ""; // allow re-picking the same file
        }}
      />

      {/* queue */}
      {queued.length > 0 && (
        <div className="space-y-2">
          <ul className="max-h-36 space-y-1 overflow-y-auto">
            {queued.map((f) => (
              <li
                key={f.name}
                className="flex items-center justify-between gap-2 rounded-lg bg-inset px-3 py-2 text-xs"
              >
                <span className="truncate">{f.name}</span>
                <button
                  onClick={() =>
                    setQueued((q) => q.filter((x) => x.name !== f.name))
                  }
                  className="shrink-0 rounded p-1 text-muted transition hover:text-red-400"
                  aria-label={`Remove ${f.name}`}
                >
                  <IconX className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
          <PrimaryButton onClick={upload} loading={busy} className="w-full">
            {busy
              ? "Uploading and indexing..."
              : `Upload ${queued.length} file${queued.length === 1 ? "" : "s"}`}
          </PrimaryButton>
        </div>
      )}

      {messages.map((m, i) => (
        <Alert
          key={i}
          kind={m.kind}
          onClose={() => setMessages((ms) => ms.filter((_, j) => j !== i))}
        >
          {m.text}
        </Alert>
      ))}
    </div>
  );
}
