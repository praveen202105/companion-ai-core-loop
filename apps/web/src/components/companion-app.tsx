"use client";

import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";

import { signOutOfMira } from "@/app/actions";
import type { ChatMessage, CompanionUser, MemoryInspectorPayload, SSEEvent } from "@/lib/contracts";
import { consumeSSE } from "@/lib/sse";

type AppState = "loading" | "ready" | "unavailable";

export function CompanionApp({ user }: { user: CompanionUser }) {
  const [appState, setAppState] = useState<AppState>("loading");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retryTurn, setRetryTurn] = useState<{ message: string; requestId: string } | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [inspector, setInspector] = useState<MemoryInspectorPayload | null>(null);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
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
    if (typeof viewport.current?.scrollTo === "function") {
      viewport.current.scrollTo({ top: viewport.current.scrollHeight, behavior: "smooth" });
    }
  }, [messages]);

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

  async function openInspector() {
    setInspectorOpen(true);
    setInspectorLoading(true);
    try {
      const response = await fetch("/api/memories", { cache: "no-store" });
      if (!response.ok) throw new Error("Could not load memory inspector");
      setInspector((await response.json()) as MemoryInspectorPayload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load memories.");
    } finally {
      setInspectorLoading(false);
    }
  }

  async function resetSession() {
    setResetting(true);
    setError(null);
    try {
      const deleted = await fetch("/api/session", { method: "DELETE" });
      if (!deleted.ok) throw new Error("Could not reset this session.");
      setMessages([]);
      setInspector(null);
      setInspectorOpen(false);
      setConfirmReset(false);
      await initializeSession();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not reset this session.");
    } finally {
      setResetting(false);
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
      const content = typeof event.data.content === "string" ? event.data.content : null;
      setMessages((current) =>
        current.map((item) =>
          item.id === assistantId
            ? { ...item, id, content: content ?? item.content }
            : item,
        ),
      );
    }
    if (event.event === "error") {
      throw new Error(String(event.data.message || "Mira could not respond just now."));
    }
  }

  if (appState === "loading") return <LoadingScreen />;
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
          <div className="header-actions">
            <button className="icon-action" onClick={() => setConfirmReset(true)} aria-label="New chat">
              <NewChatIcon />
            </button>
            <button
              className="memory-pill"
              onClick={() => void openInspector()}
              aria-label="Open memory inspector"
            >
              <SparkIcon />
              <span>{inspector?.memories.length ? `${inspector.memories.length} memories` : "memory"}</span>
            </button>
            <div className="user-chip" title={user.email || user.name || "Google account"}>
              <span>{initials(user.name || user.email)}</span>
              <div>
                <b>{user.name || "Google user"}</b>
                <small>{user.email}</small>
              </div>
            </div>
            <form action={signOutOfMira}>
              <button className="sign-out-action" type="submit" aria-label="Sign out">
                Sign out
              </button>
            </form>
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
      <MemoryInspector
        open={inspectorOpen}
        loading={inspectorLoading}
        payload={inspector}
        onClose={() => setInspectorOpen(false)}
        onReset={() => setConfirmReset(true)}
      />
      {confirmReset ? (
        <ConfirmReset
          resetting={resetting}
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => void resetSession()}
        />
      ) : null}
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

function MemoryInspector({
  open,
  loading,
  payload,
  onClose,
  onReset,
}: {
  open: boolean;
  loading: boolean;
  payload: MemoryInspectorPayload | null;
  onClose: () => void;
  onReset: () => void;
}) {
  const [tab, setTab] = useState<"memories" | "timeline">("memories");
  if (!open) return null;
  const selected = new Map(payload?.trace?.selected.map((item) => [item.memory_id, item]));
  return (
    <div className="drawer-layer" role="presentation" onMouseDown={onClose}>
      <aside
        className="memory-drawer"
        role="dialog"
        aria-modal="true"
        aria-label="Mira's memory inspector"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="drawer-header">
          <div>
            <p className="drawer-eyebrow">Transparent by design</p>
            <h2>Mira&apos;s memory</h2>
          </div>
          <button className="close-action" onClick={onClose} aria-label="Close memory inspector">
            <CloseIcon />
          </button>
        </div>
        <p className="drawer-copy">
          Only active facts can shape a reply. Old values stay in the audit timeline but are never
          retrieved.
        </p>
        <div className="drawer-tabs" role="tablist">
          <button className={tab === "memories" ? "active" : ""} onClick={() => setTab("memories")} role="tab">
            Active memories <span>{payload?.memories.length || 0}</span>
          </button>
          <button className={tab === "timeline" ? "active" : ""} onClick={() => setTab("timeline")} role="tab">
            Timeline
          </button>
        </div>

        <div className="drawer-content">
          {loading ? <InspectorSkeleton /> : null}
          {!loading && tab === "memories" ? (
            payload?.memories.length ? (
              <div className="memory-stack">
                {payload.memories.map((memory) => {
                  const retrieval = selected.get(memory.id);
                  return (
                    <article className="memory-card" key={memory.id}>
                      <div className="memory-card-top">
                        <span className={`memory-type ${memory.memory_type}`}>{memory.memory_type}</span>
                        {retrieval ? <span className="used-badge">used last turn</span> : null}
                      </div>
                      <p>{memory.normalized_text}</p>
                      <div className="memory-meta">
                        <span>{Math.round(memory.confidence * 100)}% confidence</span>
                        <span>importance {memory.importance.toFixed(1)}</span>
                        {retrieval ? <span>score {retrieval.score.toFixed(3)}</span> : null}
                      </div>
                      {retrieval ? (
                        <details>
                          <summary>Why this was selected</summary>
                          <div className="factor-grid">
                            {Object.entries(retrieval.factors)
                              .filter(([key]) => !key.endsWith("_rank"))
                              .map(([key, value]) => (
                                <span key={key}><b>{key}</b>{value.toFixed(3)}</span>
                              ))}
                          </div>
                        </details>
                      ) : null}
                    </article>
                  );
                })}
              </div>
            ) : (
              <InspectorEmpty />
            )
          ) : null}
          {!loading && tab === "timeline" ? (
            payload?.events.length ? (
              <ol className="timeline-list">
                {[...payload.events].reverse().map((event) => (
                  <li key={event.id}>
                    <span className={`event-dot ${event.action}`} />
                    <div>
                      <b>{event.action.replace("_", " ")}</b>
                      <p>{friendlyKey(event.canonical_key)}</p>
                      <small>{event.reason_code.replaceAll("_", " ")}</small>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <InspectorEmpty />
            )
          ) : null}
        </div>
        <div className="drawer-footer">
          <p>Prompts and private model reasoning are never shown here.</p>
          <button onClick={onReset}>Delete this session</button>
        </div>
      </aside>
    </div>
  );
}

function ConfirmReset({
  resetting,
  onCancel,
  onConfirm,
}: {
  resetting: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-layer" role="presentation">
      <section className="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="reset-title">
        <div className="warning-mark">!</div>
        <h2 id="reset-title">Start with a clean slate?</h2>
        <p>This permanently deletes this conversation, every memory, and its audit history.</p>
        <div className="modal-actions">
          <button className="secondary" onClick={onCancel} disabled={resetting}>Keep this chat</button>
          <button className="danger" onClick={onConfirm} disabled={resetting}>
            {resetting ? "Deleting…" : "Delete and start over"}
          </button>
        </div>
      </section>
    </div>
  );
}

function InspectorSkeleton() {
  return <div className="inspector-skeleton"><i /><i /><i /></div>;
}

function InspectorEmpty() {
  return (
    <div className="inspector-empty">
      <SparkIcon />
      <h3>Nothing saved yet</h3>
      <p>Mira only keeps stable details that may help in a later conversation.</p>
    </div>
  );
}

function friendlyKey(key: string | null) {
  if (!key) return "No canonical memory changed";
  return key.split(":").slice(2).join(" · ").replaceAll("_", " ");
}

function initials(value: string | null) {
  if (!value) return "G";
  const parts = value.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "G";
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

function NewChatIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h8" /><path d="M16 3v6M13 6h6M8 10h7M8 14h5" /></svg>;
}

function CloseIcon() {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>;
}

function TypingDots() {
  return <span className="typing-dots" aria-label="Mira is responding"><i /><i /><i /></span>;
}
