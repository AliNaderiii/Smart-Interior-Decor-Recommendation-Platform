import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { post } from "@/lib/api";
import type { AuthPayload } from "@/lib/types";
import { useAuthStore } from "@/stores/authStore";
import { Button, Card, Input } from "@/components/ui";

const schema = z.object({
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
});
type Form = z.infer<typeof schema>;

export default function LoginPage() {
  const { register, handleSubmit, formState } = useForm<Form>({ resolver: zodResolver(schema) });
  const setAuth = useAuthStore((s) => s.setAuth);
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [error, setError] = useState("");
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
      const err = e as { response?: { data?: { error?: string } } };
      setError(err.response?.data?.error ?? "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md pt-10">
      <Card className="p-8">
        <h1 className="text-2xl font-bold text-walnut">Welcome back</h1>
        <p className="mt-1 text-sm text-stone">Sign in to continue designing your living room.</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium">Email</label>
            <Input id="email" type="email" autoComplete="email" {...register("email")} />
            {formState.errors.email && <p className="mt-1 text-xs text-red-700">{formState.errors.email.message}</p>}
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium">Password</label>
            <Input id="password" type="password" autoComplete="current-password" {...register("password")} />
            {formState.errors.password && <p className="mt-1 text-xs text-red-700">{formState.errors.password.message}</p>}
          </div>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-stone">
          No account? <Link to="/register" className="font-semibold text-clay">Create one</Link>
        </p>
        <div className="mt-6 rounded-xl bg-sand p-3 text-xs text-stone">
          <p className="font-semibold text-walnut">Demo accounts</p>
          <p>demo@smartdecor.dev / Demo1234! · designer@smartdecor.dev / Design123! · admin@smartdecor.dev / Admin123!</p>
        </div>
      </Card>
    </div>
  );
}
