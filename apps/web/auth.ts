import NextAuth from "next-auth";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import { decode as defaultDecode } from "next-auth/jwt";

export const { handlers, signIn, signOut, auth } = NextAuth({
  secret: process.env.AUTH_SECRET || "authjs-dev-secret-generate-with-openssl-rand-hex-32",
  jwt: {
    async decode(params) {
      try {
        return await defaultDecode(params);
      } catch {
        // If an old stale session token was encrypted with an older secret, return null gracefully
        return null;
      }
    },
  },
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID || "",
      clientSecret: process.env.AUTH_GOOGLE_SECRET || "",
    }),
    Credentials({
      name: "Email and Password",
      credentials: {
        email: { label: "Email", type: "email", placeholder: "you@example.com" },
        password: { label: "Password", type: "password" },
      },
      authorize: async (credentials: any) => {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        const email = String(credentials.email).toLowerCase().trim();
        const password = String(credentials.password);

        try {
          const djangoUrl = process.env.DJANGO_API_URL || "http://127.0.0.1:8000";
          const res = await fetch(`${djangoUrl}/api/v1/users/verify-credentials/`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          });

          if (!res.ok) {
            return null;
          }

          const json = await res.json();
          if (json.success && json.data) {
            return {
              id: json.data.id,
              email: json.data.email,
              name: json.data.name,
            };
          }
        } catch (err) {
          console.error("Auth.js credentials verification error:", err);
        }

        return null;
      },
    }),
  ],
  callbacks: {
    authorized({ request, auth }) {
      const { pathname } = request.nextUrl;
      if (pathname.startsWith("/api/")) return true;
      if (
        pathname === "/" ||
        pathname.startsWith("/login") ||
        pathname.startsWith("/register") ||
        pathname.startsWith("/privacy") ||
        pathname.startsWith("/terms")
      ) {
        return true;
      }
      return !!auth;
    },
    jwt({ token, user }: { token: any; user?: any }) {
      if (user) {
        token.id = user.id;
        token.email = user.email;
        token.name = user.name;
      }
      return token;
    },
    session({ session, token }: { session: any; token: any }) {
      if (token && session.user) {
        session.user.id = token.id as string;
        session.user.email = token.email as string;
        session.user.name = token.name as string;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
  },
  session: {
    strategy: "jwt",
  },
  trustHost: true,
});
