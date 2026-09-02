import Link from "next/link";

import { signInWithGoogle } from "@/app/actions";

export function SignInScreen() {
  return (
    <main className="unlock-shell">
      <div className="unlock-grain" />
      <section className="unlock-card">
        <MiraMark />
        <p className="eyebrow">A small, thoughtful space</p>
        <h1>Mira remembers<br />what matters.</h1>
        <p className="unlock-copy">
          A steady companion with a long memory and a consistent point of view. Sign in to keep
          your conversation private and available across your devices.
        </p>
        <form action={signInWithGoogle}>
          <button className="google-signin" type="submit" aria-label="Continue with Google">
            <GoogleIcon />
            <span>Continue with Google</span>
          </button>
        </form>
        <p className="unlock-footnote">
          Your conversation stays until you delete it. <Link href="/privacy">Privacy</Link>
        </p>
      </section>
    </main>
  );
}

function MiraMark() {
  return <div className="mira-mark large" aria-hidden="true"><span /><i /></div>;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M21.6 12.23c0-.71-.06-1.4-.18-2.07H12v3.91h5.38a4.6 4.6 0 0 1-2 3.02v2.54h3.24c1.9-1.75 2.98-4.33 2.98-7.4Z" />
      <path fill="#34A853" d="M12 22c2.7 0 4.97-.9 6.62-2.43l-3.24-2.54c-.9.6-2.05.96-3.38.96-2.61 0-4.82-1.76-5.61-4.13H3.04v2.62A10 10 0 0 0 12 22Z" />
      <path fill="#FBBC05" d="M6.39 13.86A6.02 6.02 0 0 1 6.08 12c0-.65.11-1.28.31-1.86V7.52H3.04A10 10 0 0 0 2 12c0 1.61.38 3.14 1.04 4.48l3.35-2.62Z" />
      <path fill="#EA4335" d="M12 6.01c1.47 0 2.79.51 3.82 1.5l2.87-2.87A9.62 9.62 0 0 0 12 2a10 10 0 0 0-8.96 5.52l3.35 2.62C7.18 7.77 9.39 6.01 12 6.01Z" />
    </svg>
  );
}
