import { NextResponse } from "next/server";

import { isUnlocked } from "@/lib/server/auth";
import { backendFetch } from "@/lib/server/backend";
import { getSessionId } from "@/lib/server/session";

export const runtime = "nodejs";

export async function GET() {
  if (!(await isUnlocked())) {
    return NextResponse.json({ error: "Locked" }, { status: 401 });
  }
  const sessionId = await getSessionId();
  if (!sessionId) {
    return NextResponse.json({ error: "Session not initialized" }, { status: 409 });
  }
  const upstream = await backendFetch(`/v1/sessions/${sessionId}/memories?status=active`);
  if (!upstream.ok) {
    return NextResponse.json({ error: "Could not load memories" }, { status: 502 });
  }
  return NextResponse.json(await upstream.json());
}
