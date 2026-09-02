import NextAuth, { type DefaultSession, type NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";

import { verifiedGoogleSubject } from "@/lib/auth-profile";

declare module "next-auth" {
  interface Session {
    user: {
      id: string;
    } & DefaultSession["user"];
  }
}

export const authConfig = {
  providers: [
    Google({
      authorization: { params: { scope: "openid email profile" } },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24 * 30,
  },
  trustHost: true,
  pages: {
    signIn: "/",
  },
  callbacks: {
    async signIn({ account, profile }) {
      return account?.provider === "google" && verifiedGoogleSubject(profile) !== null;
    },
    async jwt({ token, account, profile }) {
      if (account?.provider === "google") {
        const subject = verifiedGoogleSubject(profile);
        if (subject) token.googleSubject = subject;
      }
      return token;
    },
    async session({ session, token }) {
      const subject = typeof token.googleSubject === "string" ? token.googleSubject : null;
      if (session.user && subject) {
        session.user.id = subject;
      }
      return session;
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
