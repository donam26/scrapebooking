"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";
import { api, errorMessage } from "@/lib/api";
import { Button, ErrorBox, Field, Input } from "@/components/ui";

function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.startsWith("/login")) return "/overview";
  return raw;
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.auth.login({ email: email.trim(), password });
      router.replace(safeNext(params.get("next")));
    } catch (err) {
      setError(errorMessage(err) === "invalid credentials" ? "Email hoặc mật khẩu không đúng" : errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-lg border border-line bg-surface p-6 shadow-xs">
      <div>
        <h1 className="text-lg font-semibold text-slate-900">Đăng nhập</h1>
        <p className="text-sm text-slate-500">Theo dõi đối thủ trên Booking.com</p>
      </div>
      <Field label="Email">
        <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
      </Field>
      <Field label="Mật khẩu">
        <Input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
      </Field>
      <ErrorBox error={error} />
      <Button type="submit" variant="primary" busy={busy} className="w-full">
        Đăng nhập
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
