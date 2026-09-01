import "server-only";

import { scryptSync, timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

import { AUTH_COOKIE, verifyToken } from "./tokens";

export async function isUnlocked(): Promise<boolean> {
  const store = await cookies();
  return verifyToken(store.get(AUTH_COOKIE)?.value, "auth") !== null;
}

export function verifyPasscode(passcode: string): boolean {
  const configured = process.env.DEMO_PASSCODE_HASH;
  if (configured) {
    const [algorithm, saltHex, hashHex] = configured.split("$");
    if (algorithm !== "scrypt" || !saltHex || !hashHex) return false;
    const expected = Buffer.from(hashHex, "hex");
    const actual = scryptSync(passcode, Buffer.from(saltHex, "hex"), expected.length);
    return expected.length === actual.length && timingSafeEqual(expected, actual);
  }
  if (process.env.NODE_ENV !== "production") {
    return passcode === (process.env.DEMO_PASSCODE || "companion-demo");
  }
  throw new Error("DEMO_PASSCODE_HASH is required in production");
}
