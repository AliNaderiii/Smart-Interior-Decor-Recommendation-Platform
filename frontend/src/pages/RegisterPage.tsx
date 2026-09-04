import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { post } from "@/lib/api";
import type { AuthPayload } from "@/lib/types";
import { useAuthStore } from "@/stores/authStore";
import { Button, Card, Input } from "@/components/ui";
import { useT } from "@/i18n";

const schema = z.object({
  full_name: z.string().min(2, "enterName"),
  email: z.string().email("invalidEmail"),
  password: z.string().min(8, "minChars"),
  role: z.enum(["homeowner", "designer"]),
});
type Form = z.infer<typeof schema>;

export default function RegisterPage() {
  const { register, handleSubmit, formState } = useForm<Form>({
    resolver: zodResolver(schema),
    defaultValues: { role: "homeowner" },
  });
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const t = useT();
  const [busy, setBusy] = useState(false);

  async function onSubmit(values: Form) {
    setBusy(true);
    setError("");
    try {
      const data = await post<AuthPayload>("/auth/register", values);
      setAuth(data.user, data.access_token, data.refresh_token);
      navigate(values.role === "designer" ? "/designer/dashboard" : "/quiz");
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } };
      setError(err.response?.data?.error ?? t.auth.registerFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md pt-10">
      <Card className="p-8">
        <h1 className="h1 text-[var(--color-ink)]">{t.auth.registerHeading}</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">Answer a 2-minute quiz, get a full room plan.</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="full_name" className="mb-1 block text-sm font-medium">{t.auth.fullName}</label>
            <Input id="full_name" autoComplete="name" {...register("full_name")} />
            {formState.errors.full_name && <p className="mt-1 text-xs text-red-700">{(t.auth as Record<string,string>)[formState.errors.full_name.message ?? ""] ?? formState.errors.full_name.message}</p>}
          </div>
          <div>
            <label htmlFor="reg-email" className="mb-1 block text-sm font-medium">{t.auth.email}</label>
            <Input id="reg-email" type="email" autoComplete="email" {...register("email")} />
            {formState.errors.email && <p className="mt-1 text-xs text-red-700">{(t.auth as Record<string,string>)[formState.errors.email.message ?? ""] ?? formState.errors.email.message}</p>}
          </div>
          <div>
            <label htmlFor="reg-password" className="mb-1 block text-sm font-medium">{t.auth.password}</label>
            <Input id="reg-password" type="password" autoComplete="new-password" {...register("password")} />
            {formState.errors.password && <p className="mt-1 text-xs text-red-700">{(t.auth as Record<string,string>)[formState.errors.password.message ?? ""] ?? formState.errors.password.message}</p>}
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">{t.auth.iAmA}</legend>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--color-line)] px-3 py-2.5 text-sm has-checked:border-[var(--color-accent)] has-checked:bg-[var(--color-accent)]/5">
                <input type="radio" value="homeowner" {...register("role")} className="accent-clay" />
                {t.auth.homeowner}
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[var(--color-line)] px-3 py-2.5 text-sm has-checked:border-[var(--color-accent)] has-checked:bg-[var(--color-accent)]/5">
                <input type="radio" value="designer" {...register("role")} className="accent-clay" />
                {t.auth.designer}
              </label>
            </div>
          </fieldset>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? t.auth.creating : t.auth.registerTitle}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-[var(--color-muted)]">
          {t.auth.hasAccount} <Link to="/login" className="font-semibold text-[var(--color-ink)] underline underline-offset-2">{t.auth.signInHere}</Link>
        </p>
      </Card>
    </div>
  );
}
