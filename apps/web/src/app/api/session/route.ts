import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/server/backend";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

export const runtime = "nodejs";

export async function POST() {
  const principal = await getAuthenticatedPrincipal();
  if (!principal) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const upstream = await backendFetch("/v1/me/session", { method: "POST" }, principal);
  if (!upstream.ok) {
    return NextResponse.json({ error: "Companion service unavailable" }, { status: 502 });
  }
  const body = (await upstream.json()) as { messages: unknown[] };
  return NextResponse.json({ ready: true, messages: body.messages });
}

export async function DELETE() {
  const principal = await getAuthenticatedPrincipal();
  if (!principal) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const reset = await backendFetch("/v1/me/session/reset", { method: "POST" }, principal);
  if (!reset.ok) {
    return NextResponse.json({ error: "Could not reset session" }, { status: 502 });
  }
  return NextResponse.json({ deleted: true, messages: [] });
}
