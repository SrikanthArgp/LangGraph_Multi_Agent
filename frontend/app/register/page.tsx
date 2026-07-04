"use client";

import { useState, type SubmitEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/components/AuthProvider";

export default function RegisterPage() {
  const router = useRouter();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      await register(email, username, password);
      router.replace("/chat");
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Couldn't create your account. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-600 text-sm font-semibold text-white">
            C
          </div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-50">Create your account</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Start a conversation with the assistant.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            />
          </div>

          <div>
            <label htmlFor="username" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Username
            </label>
            <input
              id="username"
              type="text"
              autoComplete="username"
              required
              minLength={3}
              maxLength={100}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              maxLength={72}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 outline-none focus:border-emerald-600 focus:ring-2 focus:ring-emerald-600/30 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50"
            />
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">At least 8 characters.</p>
          </div>

          {formError && (
            <p role="alert" className="text-sm text-red-600 dark:text-red-400">
              {formError}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-zinc-500 dark:text-zinc-400">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-emerald-600 hover:text-emerald-700 dark:text-emerald-400">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
