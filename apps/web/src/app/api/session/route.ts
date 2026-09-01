import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { isUnlocked } from "@/lib/server/auth";
import { backendFetch } from "@/lib/server/backend";
import { getSessionId } from "@/lib/server/session";
import { cookieOptions, SESSION_COOKIE, signToken } from "@/lib/server/tokens";

export const runtime = "nodejs";

export async function POST() {
  if (!(await isUnlocked())) {
    return NextResponse.json({ error: "Locked" }, { status: 401 });
  }
  let sessionId = await getSessionId();
  let messages: unknown[] = [];
  if (sessionId) {
    const existing = await backendFetch(`/v1/sessions/${sessionId}/messages`);
    if (existing.ok) {
      const body = (await existing.json()) as { messages: unknown[] };
      messages = body.messages;
    } else if (existing.status === 404) {
      sessionId = null;
    } else {
      return NextResponse.json({ error: "Companion service unavailable" }, { status: 502 });
    }
  }
  if (!sessionId) {
    const created = await backendFetch("/v1/sessions", { method: "POST" });
    if (!created.ok) {
      return NextResponse.json({ error: "Could not start a session" }, { status: 502 });
    }
    const body = (await created.json()) as {
      session: { id: string; expires_at: string };
    };
    sessionId = body.session.id;
    const maxAge = 60 * 60 * 24 * 30;
    const token = signToken({
      kind: "session",
      sessionId,
      exp: Date.now() + maxAge * 1_000,
    });
    const store = await cookies();
    store.set(SESSION_COOKIE, token, cookieOptions(maxAge));
  }
  return NextResponse.json({ ready: true, messages });
}
