import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { ApiError, post } from "@/lib/api";
import type { AuthPayload } from "@/lib/types";
import { useAuthStore } from "@/stores/authStore";
import { Button, Card, Input } from "@/components/ui";
import { useT } from "@/i18n";

const schema = z.object({
  email: z.string().email("invalidEmail"),
  password: z.string().min(8, "minChars"),
});
type Form = z.infer<typeof schema>;

export default function LoginPage() {
  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) });
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [error, setError] = useState("");
  const t = useT();
  const [busy, setBusy] = useState(false);

  async function onSubmit(values: Form) {
    setBusy(true);
    setError("");
    try {
      const data = await post<AuthPayload>("/auth/login", values);
      setAuth(data.user, data.access_token, data.refresh_token);
      const dest =
        data.user.role === "admin" ? "/admin/products"
        : data.user.role === "designer" ? "/designer/dashboard"
        : (location.state?.from ?? "/quiz");
      navigate(dest);
    } catch (e: unknown) {
      // Stage 1 (T-1.4): ApiError carries the server envelope in `.body` and
      // the server's error string as `.message` (the old code read an
      // axios-shaped `.response` this fetch-based client never produced, so
      // users always saw the generic "Login failed" instead of
      // "Invalid credentials").
      setError(e instanceof ApiError ? e.message : t.auth.loginFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md pt-10">
      <Card className="p-8">
        <h1 className="h1 text-[var(--color-ink)]">{t.auth.welcomeBack}</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">{t.auth.loginSubtitle}</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">{t.auth.email}</label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {formState.errors.email && <p className="mt-1 text-xs text-red-700">{t.auth[formState.errors.email.message as "invalidEmail"] ?? formState.errors.email.message}</p>}
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium">{t.auth.password}</label>
            <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
            {formState.errors.password && <p className="mt-1 text-xs text-red-700">{t.auth[formState.errors.password.message as "minChars"] ?? formState.errors.password.message}</p>}
          </div>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? t.auth.signingIn : t.auth.loginCta}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--color-muted)]">
          {t.auth.noAccount} <Link to="/register" className="font-semibold text-[var(--color-ink)] underline underline-offset-2">{t.auth.createOne}</Link>
        </p>
        {/* Stage 03 (T-02): the demo credentials used to be published to every
            visitor, including in production, where `admin@smartdecor.dev /
            Admin123!` was a working login. Production no longer creates those
            accounts at all (see `docs/security/DEMO_ACCOUNTS.md`), so the hint
            would be misleading as well as dangerous — it is compiled out of
            production bundles entirely by `import.meta.env.DEV`, which Vite
            resolves statically at build time. */}
        {import.meta.env.DEV && (
          <div className="mt-6 rounded-xl border border-[var(--color-line)] bg-[var(--color-canvas)] p-3 text-xs text-[var(--color-muted)]">
            <p className="font-semibold text-[var(--color-ink)]">Demo accounts (development build)</p>
            <p>
              Available only when the backend was seeded with{" "}
              <code>SEED_DEMO_ACCOUNTS=true</code> outside production.
            </p>
            <p>demo@smartdecor.dev / Demo1234! · designer@smartdecor.dev / Design123! · admin@smartdecor.dev / Admin123!</p>
          </div>
        )}
      </Card>
    </div>
  );
}
