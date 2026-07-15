"use client";

import { FormEvent, useEffect, useState } from "react";

import type { FloorChatMessage } from "@/lib/floor/types";

type ChatResponse = { messages: FloorChatMessage[] };
type SendResponse = { user: FloorChatMessage; assistant: FloorChatMessage };
type ErrorResponse = { error?: string };

export function FloorChat() {
  const [messages, setMessages] = useState<FloorChatMessage[]>([]);
  const [message, setMessage] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCurrent = true;

    async function loadMessages() {
      try {
        const response = await fetch("/api/floor/chat");
        const payload = await response.json() as ChatResponse & ErrorResponse;
        if (!response.ok) throw new Error(payload.error ?? "Could not load floor chat.");
        if (isCurrent) setMessages(payload.messages);
      } catch (loadError) {
        if (isCurrent) {
          setError(loadError instanceof Error ? loadError.message : "Could not load floor chat.");
        }
      } finally {
        if (isCurrent) setIsLoading(false);
      }
    }

    void loadMessages();
    return () => {
      isCurrent = false;
    };
  }, []);

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = message.trim();
    if (!content || isSending) return;

    setIsSending(true);
    setError(null);
    try {
      const response = await fetch("/api/floor/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: content }),
      });
      const payload = await response.json() as SendResponse & ErrorResponse;
      if (!response.ok) {
        throw new Error(
          response.status === 429
            ? "Too many messages. Please wait a moment."
            : payload.error ?? "Could not send message.",
        );
      }

      setMessages((current) => [...current, payload.user, payload.assistant]);
      setMessage("");
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : "Could not send message.");
    } finally {
      setIsSending(false);
    }
  }

  return (
    <section className="w-full max-w-full min-w-0 rounded-xl border border-line bg-card p-5" aria-label="Floor PM chat">
      <div className="border-b border-line pb-4">
        <h2 className="text-base font-semibold text-ink">Floor PM chat</h2>
        <p className="mt-1 text-sm text-slate">Ask for a read on the current desk board.</p>
      </div>

      <div className="min-h-40 space-y-3 py-4" aria-live="polite">
        {isLoading ? (
          <p className="text-sm text-slate">Loading conversation...</p>
        ) : messages.length === 0 ? (
          <p className="text-sm text-slate">No messages yet. Ask the PM about the current setup.</p>
        ) : (
          messages.map((chatMessage) => (
            <div
              key={chatMessage.id}
              className={`max-w-2xl rounded-lg border p-3 text-sm leading-6 ${
                chatMessage.role === "user"
                  ? "ml-auto border-accent/30 bg-accent-soft text-ink"
                  : "border-line bg-paper text-slate"
              }`}
            >
              <p className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-wide text-slate">
                {chatMessage.role === "user" ? "You" : "PM"}
              </p>
              <p>{chatMessage.content}</p>
            </div>
          ))
        )}
      </div>

      {error ? <p className="mb-3 text-sm text-ink" role="alert">{error}</p> : null}

      <form onSubmit={sendMessage} className="border-t border-line pt-4">
        <label htmlFor="floor-message" className="sr-only">Message the floor PM</label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <textarea
            id="floor-message"
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Ask the PM about the current setup"
            maxLength={1000}
            rows={2}
            disabled={isSending}
            className="min-h-11 flex-1 resize-y rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink outline-none placeholder:text-slate focus:border-accent focus:ring-2 focus:ring-accent/20 disabled:cursor-not-allowed disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={!message.trim() || isSending}
            className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-paper transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSending ? "Sending..." : "Send"}
          </button>
        </div>
      </form>
    </section>
  );
}
