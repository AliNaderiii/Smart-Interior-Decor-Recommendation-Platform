import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { post } from "@/lib/api";
import type { AuthPayload } from "@/lib/types";
import { useAuthStore } from "@/stores/authStore";
import { Button, Card, Input } from "@/components/ui";

const schema = z.object({
  full_name: z.string().min(2, "Enter your name"),
  email: z.string().email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
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
      setError(err.response?.data?.error ?? "Registration failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-md pt-10">
      <Card className="p-8">
        <h1 className="text-2xl font-bold text-walnut">Create your account</h1>
        <p className="mt-1 text-sm text-stone">Answer a 2-minute quiz, get a full room plan.</p>
        <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
          <div>
            <label htmlFor="full_name" className="mb-1 block text-sm font-medium">Full name</label>
            <Input id="full_name" autoComplete="name" {...register("full_name")} />
            {formState.errors.full_name && <p className="mt-1 text-xs text-red-700">{formState.errors.full_name.message}</p>}
          </div>
          <div>
            <label htmlFor="reg-email" className="mb-1 block text-sm font-medium">Email</label>
            <Input id="reg-email" type="email" autoComplete="email" {...register("email")} />
            {formState.errors.email && <p className="mt-1 text-xs text-red-700">{formState.errors.email.message}</p>}
          </div>
          <div>
            <label htmlFor="reg-password" className="mb-1 block text-sm font-medium">Password</label>
            <Input id="reg-password" type="password" autoComplete="new-password" {...register("password")} />
            {formState.errors.password && <p className="mt-1 text-xs text-red-700">{formState.errors.password.message}</p>}
          </div>
          <fieldset>
            <legend className="mb-1 text-sm font-medium">I am a…</legend>
            <div className="grid grid-cols-2 gap-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[#e5ded3] px-3 py-2.5 text-sm has-checked:border-clay has-checked:bg-[#fdf3ee]">
                <input type="radio" value="homeowner" {...register("role")} className="accent-clay" />
                Homeowner
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-[#e5ded3] px-3 py-2.5 text-sm has-checked:border-clay has-checked:bg-[#fdf3ee]">
                <input type="radio" value="designer" {...register("role")} className="accent-clay" />
                Interior Designer
              </label>
            </div>
          </fieldset>
          {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Creating…" : "Create account"}
          </Button>
        </form>
        <p className="mt-4 text-center text-sm text-stone">
          Already registered? <Link to="/login" className="font-semibold text-clay">Sign in</Link>
        </p>
      </Card>
    </div>
  );
}
