import "server-only";

import { cookies } from "next/headers";

import { auth } from "@/auth";

export type AuthenticatedPrincipal = {
  provider: "google";
  subject: string;
  name: string | null;
  email: string | null;
  image: string | null;
};

const E2E_SUBJECT_COOKIE = "e2e_auth_subject";

export async function getAuthenticatedPrincipal(): Promise<AuthenticatedPrincipal | null> {
  if (process.env.E2E_AUTH_BYPASS === "true" && process.env.NODE_ENV !== "production") {
    const subject = (await cookies()).get(E2E_SUBJECT_COOKIE)?.value.trim();
    if (!subject || subject.length > 255) return null;
    return {
      provider: "google",
      subject,
      name: `Test ${subject}`,
      email: `${subject}@example.test`,
      image: null,
    };
  }

  const session = await auth();
  const user = session?.user;
  const subject = user?.id?.trim();
  if (!user || !subject || subject.length > 255) return null;
  return {
    provider: "google",
    subject,
    name: user.name ?? null,
    email: user.email ?? null,
    image: user.image ?? null,
  };
}
