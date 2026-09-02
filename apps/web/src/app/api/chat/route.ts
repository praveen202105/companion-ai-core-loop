import { NextResponse } from "next/server";
import { z } from "zod";

import { backendFetch } from "@/lib/server/backend";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

export const runtime = "nodejs";

const bodySchema = z
  .object({
    request_id: z.string().min(8).max(80),
    message: z.string().trim().min(1).max(4_000),
  })
  .strict();

export async function POST(request: Request) {
  const principal = await getAuthenticatedPrincipal();
  if (!principal) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: "Invalid message" }, { status: 400 });
  }
  const upstream = await backendFetch("/v1/me/chat", {
    method: "POST",
    headers: { "X-Request-ID": parsed.data.request_id },
    body: JSON.stringify(parsed.data),
  }, principal);
  if (!upstream.ok || !upstream.body) {
    return NextResponse.json({ error: "Companion service unavailable" }, { status: 502 });
  }
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
    },
  });
}
