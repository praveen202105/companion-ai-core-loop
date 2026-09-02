import { NextResponse } from "next/server";

import { backendFetch } from "@/lib/server/backend";
import { getAuthenticatedPrincipal } from "@/lib/server/principal";

export const runtime = "nodejs";

export async function GET() {
  const principal = await getAuthenticatedPrincipal();
  if (!principal) return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  const upstream = await backendFetch("/v1/me/memories?status=active", {}, principal);
  if (!upstream.ok) {
    return NextResponse.json({ error: "Could not load memories" }, { status: 502 });
  }
  return NextResponse.json(await upstream.json());
}
