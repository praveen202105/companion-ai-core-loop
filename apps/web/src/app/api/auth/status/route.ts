import { NextResponse } from "next/server";

import { isUnlocked } from "@/lib/server/auth";

export const runtime = "nodejs";

export async function GET() {
  return NextResponse.json({ unlocked: await isUnlocked() });
}
