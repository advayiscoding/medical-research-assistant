"use client";

// The conversation view: message thread on the left, live citations panel on
// the right. Renders inline [n] markers in assistant messages as small badges
// so they visually tie to the sources panel. The citations panel tracks the
// most recent assistant answer.

import { useEffect, useRef, useState } from "react";
import { Send, AlertTriangle } from "lucide-react";
import { api, ApiError } from "@/lib/api";
import { Button } from "@/components/ui";
import { CitationsPanel } from "@/components/CitationsPanel";
import type { ChatMessage, Citation } from "@/lib/types";

function renderWithMarkers(content: string) {
  // Split on [n] and render the numbers as inline badges. Purely presentational
  // — the authoritative mapping lives in the citations array.
  return content.split(/(\[\d+\])/g).map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      return (
        <sup
          key={i}
          className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded bg-cyan-100 px-1 text-[10px] font-semibold text-cyan-800"
        >
          {m[1]}
        </sup>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export function ChatView({
  sessionId,
  initialMessages,
}: {
  sessionId: string;
  initialMessages: ChatMessage[];
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  // Citations shown = those of the latest assistant message.
  const latestAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const latestCitations: Citation[] = latestAssistant?.citations ?? [];
  // A refusal answer carries our fixed "not enough evidence" phrase; in that
  // case any cited chunks are off-topic, so we suppress them and say so instead
  // of presenting irrelevant papers as if they backed an answer.
  const latestInsufficient =
    !!latestAssistant &&
    latestAssistant.content.includes("do not contain enough evidence");

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const question = input.trim();
    if (question.length < 3 || sending) return;

    setInput("");
    setError(null);
    setSending(true);
    // Optimistically append the user's turn.
    const optimistic: ChatMessage = {
      id: `tmp-${Date.now()}`,
      role: "user",
      content: question,
      created_at: new Date().toISOString(),
      citations: [],
    };
    setMessages((prev) => [...prev, optimistic]);

    try {
      const res = await api.postMessage(sessionId, question);
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== optimistic.id),
        res.user_message,
        res.assistant_message,
      ]);
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
      setInput(question); // restore so the user doesn't lose their text
      setError(err instanceof ApiError ? err.message : "Failed to send.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-full">
      {/* Conversation column */}
      <div className="flex flex-1 flex-col">
        <div ref={threadRef} className="scrollbar-thin flex-1 overflow-y-auto px-8 py-6">
          <div className="mx-auto max-w-2xl space-y-5">
            {messages.length === 0 && (
              <div className="mt-20 text-center text-[var(--color-muted-foreground)]">
                <p className="font-sans text-lg font-medium text-[var(--color-foreground)]">
                  Ask a medical research question
                </p>
                <p className="mt-1 text-sm">
                  Answers are grounded only in retrieved literature, with citations.
                </p>
              </div>
            )}
            {messages.map((m) => (
              <div
                key={m.id}
                className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
              >
                <div
                  className={
                    m.role === "user"
                      ? "max-w-[85%] rounded-2xl rounded-br-sm bg-[var(--color-primary)] px-4 py-2.5 text-sm text-white"
                      : "max-w-[85%] rounded-2xl rounded-bl-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-sm leading-relaxed"
                  }
                >
                  {m.role === "assistant" ? renderWithMarkers(m.content) : m.content}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl rounded-bl-sm border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
                  <span className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <span
                        key={i}
                        className="h-2 w-2 animate-bounce rounded-full bg-[var(--color-muted-foreground)]"
                        style={{ animationDelay: `${i * 0.15}s` }}
                      />
                    ))}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        <form onSubmit={send} className="border-t border-[var(--color-border)] bg-[var(--color-surface)] px-8 py-4">
          <div className="mx-auto flex max-w-2xl items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) send(e);
              }}
              rows={1}
              placeholder="Ask a follow-up… (Enter to send, Shift+Enter for newline)"
              className="max-h-32 flex-1 resize-none rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5 text-sm outline-none focus:border-[var(--color-ring)]"
              aria-label="Message"
            />
            <Button type="submit" disabled={sending || input.trim().length < 3}>
              <Send size={16} aria-hidden />
              Send
            </Button>
          </div>
          {error && (
            <p role="alert" className="mx-auto mt-2 flex max-w-2xl items-center gap-1.5 text-sm text-red-700">
              <AlertTriangle size={14} aria-hidden /> {error}
            </p>
          )}
        </form>
      </div>

      {/* Citations panel */}
      <aside className="scrollbar-thin w-80 shrink-0 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface-muted)]">
        <CitationsPanel
          citations={latestInsufficient ? [] : latestCitations}
          insufficient={latestInsufficient}
        />
      </aside>
    </div>
  );
}
