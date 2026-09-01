"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import type { ChatMessage, SSEEvent } from "@/lib/contracts";
import { consumeSSE } from "@/lib/sse";

type AppState = "loading" | "locked" | "ready" | "unavailable";

export function CompanionApp() {
  const [appState, setAppState] = useState<AppState>("loading");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTurn, setRetryTurn] = useState<{ message: string; requestId: string } | null>(null);
  const viewport = useRef<HTMLDivElement>(null);

  const initializeSession = useCallback(async () => {
    const response = await fetch("/api/session", { method: "POST" });
    if (!response.ok) throw new Error("Session unavailable");
    const body = (await response.json()) as { messages: ChatMessage[] };
    setMessages(body.messages);
    setAppState("ready");
  }, []);

  const bootstrap = useCallback(async () => {
    try {
      const status = await fetch("/api/auth/status", { cache: "no-store" });
      const body = (await status.json()) as { unlocked: boolean };
      if (!body.unlocked) {
        setAppState("locked");
        return;
      }
      await initializeSession();
    } catch {
      setAppState("unavailable");
    }
  }, [initializeSession]);

  useEffect(() => {
    const task = window.setTimeout(() => void bootstrap(), 0);
    return () => window.clearTimeout(task);
  }, [bootstrap]);

  useEffect(() => {
    viewport.current?.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function unlocked() {
    setAppState("loading");
    try {
      await initializeSession();
    } catch {
      setAppState("unavailable");
    }
  }

  async function sendMessage(message: string, requestId = crypto.randomUUID()) {
    if (sending) return;
    const clean = message.trim();
    if (!clean) return;
    const userId = `user-${requestId}`;
    const assistantId = `assistant-${requestId}`;
    setError(null);
    setRetryTurn(null);
    setSending(true);
    setMessages((current) => [
      ...current.filter((item) => item.id !== userId && item.id !== assistantId),
      {
        id: userId,
        role: "user",
        content: clean,
        created_at: new Date().toISOString(),
      },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
      },
    ]);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, message: clean }),
      });
      await consumeSSE(response, (event) => handleEvent(event, assistantId));
    } catch (caught) {
      setMessages((current) => current.filter((item) => item.id !== assistantId));
      setError(caught instanceof Error ? caught.message : "Mira could not respond just now.");
      setRetryTurn({ message: clean, requestId });
    } finally {
      setSending(false);
    }
  }

  function handleEvent(event: SSEEvent, assistantId: string) {
    if (event.event === "message.delta") {
      const delta = String(event.data.delta || "");
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId ? { ...item, content: item.content + delta } : item,
        ),
      );
    }
    if (event.event === "message.completed") {
      const id = String(event.data.id || assistantId);
      setMessages((current) =>
        current.map((item) => (item.id === assistantId ? { ...item, id } : item)),
      );
    }
    if (event.event === "error") {
      throw new Error(String(event.data.message || "Mira could not respond just now."));
    }
  }

  if (appState === "loading") return <LoadingScreen />;
  if (appState === "locked") return <UnlockScreen onUnlocked={unlocked} />;
  if (appState === "unavailable") {
    return (
      <StatusScreen
        title="The room is quiet for a moment."
        detail="The companion service could not be reached. Check the deployment and try again."
        action={() => void bootstrap()}
      />
    );
  }

  return (
    <main className="app-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <section className="chat-card" aria-label="Conversation with Mira">
        <header className="chat-header">
          <div className="brand-lockup">
            <MiraMark />
            <div>
              <div className="brand-name">Mira</div>
              <div className="presence"><span /> here with you</div>
            </div>
          </div>
          <div className="memory-pill" title="Long-term memory is active">
            <SparkIcon />
            <span>memory on</span>
          </div>
        </header>

        <div className="message-viewport" ref={viewport} aria-live="polite">
          {messages.length === 0 ? <EmptyConversation onPrompt={sendMessage} /> : null}
          <div className="message-list">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} sending={sending} />
            ))}
          </div>
        </div>

        <div className="composer-wrap">
          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              {retryTurn ? (
                <button onClick={() => void sendMessage(retryTurn.message, retryTurn.requestId)}>
                  Try again
                </button>
              ) : null}
            </div>
          ) : null}
          <MessageComposer disabled={sending} onSend={sendMessage} />
          <p className="privacy-note">Private by default · Mira can make mistakes</p>
        </div>
      </section>
    </main>
  );
}

function UnlockScreen({ onUnlocked }: { onUnlocked: () => void }) {
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/unlock", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode }),
      });
      if (!response.ok) {
        const body = (await response.json()) as { error?: string };
        throw new Error(body.error || "That passcode did not match.");
      }
      onUnlocked();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not unlock this demo.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="unlock-shell">
      <div className="unlock-grain" />
      <section className="unlock-card">
        <MiraMark large />
        <p className="eyebrow">A small, thoughtful space</p>
        <h1>Mira remembers<br />what matters.</h1>
        <p className="unlock-copy">
          A steady companion with a long memory and a consistent point of view. This private demo
          needs the shared passcode.
        </p>
        <form onSubmit={submit} className="unlock-form">
          <label htmlFor="passcode">Demo passcode</label>
          <div className="unlock-input-row">
            <input
              id="passcode"
              name="passcode"
              type="password"
              autoComplete="current-password"
              value={passcode}
              onChange={(event) => setPasscode(event.target.value)}
              placeholder="Enter passcode"
              required
              autoFocus
            />
            <button type="submit" disabled={submitting || !passcode} aria-label="Unlock Mira">
              {submitting ? <span className="spinner" /> : <ArrowIcon />}
            </button>
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
        </form>
        <p className="unlock-footnote">Your session expires automatically after 30 days.</p>
      </section>
    </main>
  );
}

function EmptyConversation({ onPrompt }: { onPrompt: (message: string) => void }) {
  const prompts = ["I had a long day", "Remember my favorite drink", "Let’s make a small plan"];
  return (
    <div className="empty-state">
      <MiraMark large />
      <h1>Hey, I&apos;m Mira.</h1>
      <p>What&apos;s been taking up space in your head today?</p>
      <div className="prompt-row">
        {prompts.map((prompt) => (
          <button key={prompt} onClick={() => onPrompt(prompt)}>{prompt}</button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ message, sending }: { message: ChatMessage; sending: boolean }) {
  const isAssistant = message.role === "assistant";
  return (
    <article className={`message-row ${isAssistant ? "mira-row" : "user-row"}`}>
      {isAssistant ? <div className="mini-mark"><MiraMark /></div> : null}
      <div className={`bubble ${isAssistant ? "mira-bubble" : "user-bubble"}`}>
        {message.content || (sending ? <TypingDots /> : null)}
      </div>
    </article>
  );
}

function MessageComposer({ disabled, onSend }: { disabled: boolean; onSend: (value: string) => void }) {
  const [value, setValue] = useState("");
  function submit() {
    if (!value.trim() || disabled) return;
    onSend(value);
    setValue("");
  }
  function keyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }
  return (
    <div className="composer">
      <textarea
        aria-label="Message Mira"
        placeholder="Tell Mira what’s on your mind…"
        rows={1}
        maxLength={4_000}
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={keyDown}
      />
      <button onClick={submit} disabled={disabled || !value.trim()} aria-label="Send message">
        <ArrowIcon />
      </button>
    </div>
  );
}

function LoadingScreen() {
  return <main className="status-shell"><MiraMark large /><span className="loading-line" /></main>;
}

function StatusScreen({ title, detail, action }: { title: string; detail: string; action: () => void }) {
  return (
    <main className="status-shell">
      <MiraMark large />
      <h1>{title}</h1>
      <p>{detail}</p>
      <button className="primary-action" onClick={action}>Try again</button>
    </main>
  );
}

function MiraMark({ large = false }: { large?: boolean }) {
  return <div className={`mira-mark ${large ? "large" : ""}`} aria-hidden="true"><span /><i /></div>;
}

function ArrowIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-4.4 14-3.2-5.7L5 12Z" /><path d="m11.4 13.3 3.5-3.5" /></svg>;
}

function SparkIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3c.6 4.7 3.3 7.4 8 8-4.7.6-7.4 3.3-8 8-.6-4.7-3.3-7.4-8-8 4.7-.6 7.4-3.3 8-8Z" /></svg>;
}

function TypingDots() {
  return <span className="typing-dots" aria-label="Mira is responding"><i /><i /><i /></span>;
}
