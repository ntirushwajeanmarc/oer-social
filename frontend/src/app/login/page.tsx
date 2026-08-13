"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api, saveAuth } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await api.login({ email: email.trim(), password });
      saveAuth(res.access_token, res.user);
      await new Promise((r) => setTimeout(r, 50));
      router.push(res.user.role === "admin" ? "/admin" : "/feed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-4 py-10 sm:px-6 sm:py-16"
      style={{
        paddingTop: "max(2.5rem, env(safe-area-inset-top))",
        paddingBottom: "max(2.5rem, env(safe-area-inset-bottom))",
      }}
    >
      <Link href="/" className="font-display text-2xl tracking-tight text-fjord">
        OER Social
      </Link>
      <p className="mt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-mist">
        Clinical learning platform
      </p>
      <h1 className="mt-5 font-display text-[1.85rem] tracking-tight text-fjord sm:text-4xl">
        Log in
      </h1>
      <p className="mt-2 text-sm text-ink/55">
        Access your learning feed or admin workspace.
      </p>
      <form
        method="post"
        action="/login"
        autoComplete="on"
        onSubmit={onSubmit}
        className="panel mt-8 space-y-4 p-5 sm:p-6"
      >
        <label className="block" htmlFor="login-email">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
            Email
          </span>
          <input
            id="login-email"
            name="username"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-field"
          />
        </label>
        <label className="block" htmlFor="login-password">
          <span className="mb-1.5 block text-xs uppercase tracking-[0.16em] text-glacier">
            Password
          </span>
          <input
            id="login-password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input-field"
          />
        </label>
        {error ? <p className="text-sm text-red-700/80">{error}</p> : null}
        <button type="submit" disabled={loading} className="btn-primary w-full">
          {loading ? "Signing in…" : "Log in"}
        </button>
      </form>
      <p className="mt-6 text-sm text-ink/55">
        New learner?{" "}
        <Link href="/signup" className="text-fjord underline underline-offset-4">
          Create an account
        </Link>
      </p>
    </div>
  );
}
