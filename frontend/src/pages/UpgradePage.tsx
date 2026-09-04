import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { get, post } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { formatToman } from "@/lib/constants";
import { Button, Card } from "@/components/ui";
import plansData from "@/assets/subscription_plans.json";

interface SubInfo { plan: string; is_active: boolean; expires_at: string | null; pro_price_toman: number }
type Plan = {
  id: string; name_fa: string; name_en: string; price_monthly: number;
  price_yearly?: number; yearly_discount?: string; features: string[];
  cta_fa: string; popular?: boolean; badge?: string;
};

function PlanGrid({ title, plans, busy, active, onPayment }: {
  title: string; plans: Plan[]; busy: boolean; active: boolean; onPayment: () => void;
}) {
  return (
    <section className="mt-10">
      <h2 className="text-2xl font-semibold text-[var(--color-ink)]">{title}</h2>
      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        {plans.map((plan) => (
          <Card key={plan.id} className={`relative flex flex-col p-6 ${plan.popular ? "ring-2 ring-[var(--color-accent)]" : ""}`}>
            {plan.badge && <span className="absolute -top-3 right-5 rounded-full bg-[var(--color-accent)] px-3 py-1 text-xs font-semibold text-white">{plan.badge}</span>}
            <h3 className="text-xl font-semibold">{plan.name_fa}</h3>
            <p className="text-xs text-[var(--color-muted)]">{plan.name_en}</p>
            <p className="mt-5 text-2xl font-semibold tabular-nums">{formatToman(plan.price_monthly)} <span className="text-xs font-normal text-[var(--color-muted)]">/ ماه</span></p>
            {plan.price_yearly !== undefined && plan.price_yearly > 0 && <p className="mt-1 text-xs text-[var(--color-muted)]">سالانه {formatToman(plan.price_yearly)} · {plan.yearly_discount}</p>}
            <ul className="mt-5 flex-1 space-y-2 text-sm">{plan.features.map((feature) => <li key={feature}>✓ {feature}</li>)}</ul>
            <Button className="mt-6 w-full" variant={plan.popular ? "accent" : "secondary"}
                    disabled={busy || plan.price_monthly === 0 || active}
                    onClick={onPayment}>{plan.price_monthly === 0 ? "پلن فعلی" : plan.cta_fa}</Button>
          </Card>
        ))}
      </div>
    </section>
  );
}

export default function UpgradePage() {
  const [sub, setSub] = useState<SubInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();

  useEffect(() => { get<SubInfo>("/subscriptions/me").then(setSub).catch(() => {}); }, []);
  useEffect(() => {
    const authority = params.get("Authority");
    if (!authority) return;
    void (async () => {
      setBusy(true);
      try {
        const result = await post<{ status: string }>("/payment/verify", { authority, status: params.get("Status") ?? "NOK" });
        if (result.status === "paid") {
          setMessage("پرداخت تأیید شد؛ به پلن حرفه‌ای خوش آمدید 🎉");
          if (user) setUser({ ...user, subscription_active: true, subscription_plan: "pro" });
          setTimeout(() => navigate("/recommendations"), 1200);
        } else setMessage("پرداخت کامل نشد.");
      } finally { setBusy(false); }
    })();
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  async function startPayment() {
    setBusy(true);
    try {
      const res = await post<{ redirect_url?: string }>("/payment/request");
      if (!res.redirect_url) { setMessage("درگاه پرداخت پاسخی نداد؛ دوباره تلاش کنید."); return; }
      if (res.redirect_url.startsWith("http") && !res.redirect_url.includes(window.location.host)) window.location.href = res.redirect_url;
      else {
        const url = new URL(res.redirect_url, window.location.origin);
        navigate(`/upgrade?${url.searchParams.toString()}`);
      }
    } catch { setMessage("شروع پرداخت ممکن نشد؛ دوباره تلاش کنید."); }
    finally { setBusy(false); }
  }

  return (
    <div className="mx-auto max-w-6xl pb-12 pt-6">
      <div className="text-center">
        <h1 className="text-3xl font-semibold text-[var(--color-ink)]">پلن مناسب خودت را انتخاب کن</h1>
        <p className="mt-2 text-sm text-[var(--color-muted)]">پرداخت امن زرین‌پال؛ اطلاعات کارت هرگز در این سامانه ذخیره نمی‌شود.</p>
        {sub?.is_active && <p className="mt-4 text-sm text-[var(--color-ok)]">اشتراک فعال تا {sub.expires_at ? new Date(sub.expires_at).toLocaleDateString("fa-IR") : "—"}</p>}
        {message && <p className="mx-auto mt-4 max-w-lg rounded-xl border border-[var(--color-line)] p-3 text-sm">{message}</p>}
      </div>
      <PlanGrid title="برای خانه" plans={plansData.homeowner_plans as Plan[]} busy={busy} active={Boolean(sub?.is_active)} onPayment={startPayment} />
      <PlanGrid title="برای طراحان" plans={plansData.designer_plans as Plan[]} busy={busy} active={Boolean(sub?.is_active)} onPayment={startPayment} />
    </div>
  );
}
