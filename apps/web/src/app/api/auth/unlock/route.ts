import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { z } from "zod";

import { verifyPasscode } from "@/lib/server/auth";
import { AUTH_COOKIE, cookieOptions, signToken } from "@/lib/server/tokens";

export const runtime = "nodejs";

const bodySchema = z.object({ passcode: z.string().min(1).max(256) }).strict();

export async function POST(request: Request) {
  const parsed = bodySchema.safeParse(await request.json().catch(() => null));
  if (!parsed.success || !verifyPasscode(parsed.data.passcode)) {
    return NextResponse.json({ error: "That passcode did not match." }, { status: 401 });
  }
  const maxAge = 60 * 60 * 8;
  const token = signToken({ kind: "auth", exp: Date.now() + maxAge * 1_000 });
  const store = await cookies();
  store.set(AUTH_COOKIE, token, cookieOptions(maxAge));
  return NextResponse.json({ unlocked: true });
}
