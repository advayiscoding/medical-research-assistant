"use client";

import { useEffect, useRef, useState } from "react";
import { Upload, FileText, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { PageHeader } from "@/components/PageHeader";
import { Button, Card, Badge } from "@/components/ui";
import type { DocumentItem } from "@/lib/types";

function StatusBadge({ status }: { status: DocumentItem["status"] }) {
  if (status === "ready")
    return (
      <Badge tone="success">
        <CheckCircle2 size={12} className="mr-1" aria-hidden /> Ready
      </Badge>
    );
  if (status === "failed")
    return (
      <Badge tone="danger">
        <XCircle size={12} className="mr-1" aria-hidden /> Failed
      </Badge>
    );
  return (
    <Badge tone="processing">
      <Loader2 size={12} className="mr-1 animate-spin" aria-hidden /> Processing
    </Badge>
  );
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.listDocuments().then(setDocs).catch(() => {});
  }, []);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const res = await api.uploadDocument(file);
      setDocs((prev) => [res.document, ...prev]);
      if (res.document.status === "failed") {
        setError(res.document.error ?? "Processing failed.");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="flex h-dvh flex-col">
      <PageHeader
        title="Documents"
        subtitle="Upload PDFs to make your own papers searchable in Chat."
        action={
          <>
            <input
              ref={inputRef}
              type="file"
              accept="application/pdf"
              onChange={onFile}
              className="hidden"
            />
            <Button onClick={() => inputRef.current?.click()} disabled={uploading}>
              <Upload size={16} aria-hidden />
              {uploading ? "Uploading…" : "Upload PDF"}
            </Button>
          </>
        }
      />
      <div className="flex-1 overflow-y-auto px-8 py-6">
        {error && (
          <p role="alert" className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
          </p>
        )}

        {docs.length === 0 ? (
          <div className="mt-16 flex flex-col items-center text-center text-[var(--color-muted-foreground)]">
            <FileText size={40} className="mb-3 opacity-50" aria-hidden />
            <p className="font-sans text-lg font-medium text-[var(--color-foreground)]">
              No documents yet
            </p>
            <p className="mt-1 text-sm">Upload a research PDF to index it for retrieval.</p>
          </div>
        ) : (
          <div className="space-y-2">
            {docs.map((d) => (
              <Card key={d.id} className="flex items-center justify-between p-4">
                <div className="flex min-w-0 items-center gap-3">
                  <FileText size={18} className="shrink-0 text-[var(--color-primary)]" aria-hidden />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{d.title || d.filename}</p>
                    <p className="truncate text-xs text-[var(--color-muted-foreground)]">
                      {d.filename}
                      {d.status === "failed" && d.error ? ` — ${d.error}` : ""}
                    </p>
                  </div>
                </div>
                <StatusBadge status={d.status} />
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
