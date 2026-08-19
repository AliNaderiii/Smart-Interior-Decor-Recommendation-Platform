import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { get, post } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { formatToman } from "@/lib/constants";
import { Button, Card } from "@/components/ui";

interface SubInfo {
  plan: string;
  is_active: boolean;
  expires_at: string | null;
  pro_price_toman: number;
}

export default function UpgradePage() {
  const [sub, setSub] = useState<SubInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { user, setUser } = useAuthStore();

  useEffect(() => {
    get<SubInfo>("/subscriptions/me").then(setSub).catch(() => {});
  }, []);

  // Zarinpal-style callback: ?Authority=...&Status=OK
  useEffect(() => {
    const authority = params.get("Authority");
    const status = params.get("Status");
    if (!authority) return;
    (async () => {
      setBusy(true);
      try {
        const result = await post<{ status: string }>("/payment/verify", {
          authority,
          status: status ?? "NOK",
        });
        if (result.status === "paid") {
          setMessage("Payment confirmed — welcome to Pro! 🎉");
          if (user) setUser({ ...user, subscription_active: true, subscription_plan: "pro" });
          setTimeout(() => navigate("/recommendations"), 1200);
        } else {
          setMessage("Payment was not completed.");
        }
      } finally {
        setBusy(false);
      }
    })();
  }, [params]); // eslint-disable-line react-hooks/exhaustive-deps

  async function startPayment() {
    setBusy(true);
    try {
      const { redirect_url } = await post<{ redirect_url: string }>("/payment/request");
      // Sandbox/mock returns our own callback URL; production redirects to Zarinpal.
      if (redirect_url.startsWith("http") && !redirect_url.includes(window.location.host)) {
        window.location.href = redirect_url;
      } else {
        const url = new URL(redirect_url, window.location.origin);
        navigate(`/upgrade?${url.searchParams.toString()}`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg pt-8">
      <Card className="p-8 text-center">
        <span className="inline-block rounded-full bg-[#f7e3d9] px-3 py-1 text-xs font-bold uppercase tracking-wide text-clay-dark">
          Smart Decor Pro
        </span>
        <h1 className="mt-4 text-3xl font-bold text-walnut">See every match</h1>
        <p className="mt-2 text-sm text-stone">
          Free accounts see the top pick per category. Pro unlocks all 3–5 ranked matches,
          full explainability, moodboards and the shopping list.
        </p>
        <p className="mt-6 text-3xl font-extrabold text-clay-dark">
          {sub ? formatToman(sub.pro_price_toman) : "—"}
          <span className="text-sm font-medium text-stone"> / 30 days</span>
        </p>
        <ul className="mx-auto mt-6 max-w-xs space-y-2 text-left text-sm">
          {["All ranked recommendations per category", "Why-recommended breakdowns", "Unlimited moodboards", "Validated seller links"].map((f) => (
            <li key={f} className="flex items-start gap-2">
              <span className="text-sage">✓</span> {f}
            </li>
          ))}
        </ul>
        {message && <p className="mt-4 rounded-lg bg-sand px-3 py-2 text-sm font-medium">{message}</p>}
        {sub?.is_active ? (
          <p className="mt-6 rounded-xl bg-[#e7efe4] px-4 py-3 text-sm font-semibold text-sage">
            You are on Pro until {sub.expires_at ? new Date(sub.expires_at).toLocaleDateString() : "—"}
          </p>
        ) : (
          <Button className="mt-6 w-full" onClick={startPayment} disabled={busy}>
            {busy ? "Redirecting to gateway…" : "Pay with Zarinpal"}
          </Button>
        )}
        <p className="mt-3 text-xs text-stone">
          Secure redirect to the payment gateway — we never see or store card details.
        </p>
      </Card>
    </div>
  );
}
