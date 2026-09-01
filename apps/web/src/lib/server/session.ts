import "server-only";

import { cookies } from "next/headers";

import { SESSION_COOKIE, verifyToken } from "./tokens";

export async function getSessionId(): Promise<string | null> {
  const store = await cookies();
  const token = verifyToken(store.get(SESSION_COOKIE)?.value, "session");
  return token?.sessionId || null;
}
