import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";

export const AUTH_COOKIE = "companion_auth";
export const SESSION_COOKIE = "companion_session";

type SignedPayload = {
  kind: "auth" | "session";
  exp: number;
  sessionId?: string;
};

function secret(): string {
  const value = process.env.COOKIE_SIGNING_SECRET;
  if (!value || value.length < 24) {
    if (process.env.NODE_ENV !== "production") {
      return "local-cookie-secret-change-me";
    }
    throw new Error("COOKIE_SIGNING_SECRET must contain at least 24 characters");
  }
  return value;
}

export function signToken(payload: SignedPayload): string {
  const encoded = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const signature = createHmac("sha256", secret()).update(encoded).digest("base64url");
  return `${encoded}.${signature}`;
}

export function verifyToken(token: string | undefined, kind: SignedPayload["kind"]): SignedPayload | null {
  if (!token) return null;
  const [encoded, supplied] = token.split(".");
  if (!encoded || !supplied) return null;
  const expected = createHmac("sha256", secret()).update(encoded).digest();
  let suppliedBuffer: Buffer;
  try {
    suppliedBuffer = Buffer.from(supplied, "base64url");
  } catch {
    return null;
  }
  if (expected.length !== suppliedBuffer.length || !timingSafeEqual(expected, suppliedBuffer)) {
    return null;
  }
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString()) as SignedPayload;
    if (payload.kind !== kind || payload.exp <= Date.now()) return null;
    return payload;
  } catch {
    return null;
  }
}

export function cookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
    maxAge,
  };
}
