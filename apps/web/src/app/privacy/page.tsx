import Link from "next/link";

export default function PrivacyPage() {
  return (
    <main className="legal-shell">
      <article>
        <p className="eyebrow">Mira</p>
        <h1>Privacy</h1>
        <p>
          Google Sign-In is used only to identify your account. Mira stores your conversation and
          extracted memories so they remain available when you return. Google access and refresh
          tokens are not stored by the Companion API.
        </p>
        <p>
          Your messages are sent to the configured AI provider to generate replies. Normal
          application logs exclude message contents and use hashed user identifiers.
        </p>
        <p>
          Choosing New chat permanently deletes your current conversation, memories, retrieval
          traces, and audit history. Signing out does not delete this data.
        </p>
        <Link href="/">Back to Mira</Link>
      </article>
    </main>
  );
}
