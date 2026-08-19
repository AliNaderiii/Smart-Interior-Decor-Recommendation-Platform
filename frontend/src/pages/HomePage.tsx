import { Link } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { STYLES } from "@/lib/constants";
import { Card } from "@/components/ui";

export default function HomePage() {
  const user = useAuthStore((s) => s.user);
  const cta = user
    ? user.role === "admin" ? "/admin/products"
      : user.role === "designer" ? "/designer/dashboard"
      : "/quiz"
    : "/register";

  return (
    <div>
      <section className="grid items-center gap-10 py-10 lg:grid-cols-2">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-clay-dark">Living room MVP</p>
          <h1 className="mt-3 text-4xl font-extrabold leading-tight text-walnut sm:text-5xl">
            Your dream living room, matched by AI.
          </h1>
          <p className="mt-4 max-w-md text-stone">
            Answer a 2-minute style quiz. Get 3–5 ranked products per category with
            transparent “why recommended” scores, an editable moodboard, a 2D floorplan
            and a validated shopping list.
          </p>
          <div className="mt-6 flex gap-3">
            <Link to={cta} className="rounded-xl bg-clay px-6 py-3 font-semibold text-white hover:bg-clay-dark">
              {user ? "Continue" : "Start the style quiz"}
            </Link>
            {!user && (
              <Link to="/login" className="rounded-xl bg-sand px-6 py-3 font-semibold text-walnut hover:bg-[#e8e0d4]">
                Sign in
              </Link>
            )}
          </div>
        </div>
        <img
          src="https://images.unsplash.com/photo-1586023492125-27b2c045efd7?w=960&q=70&fm=webp"
          alt="Warm modern living room with a beige sofa and walnut coffee table"
          width={960} height={640}
          fetchPriority="high"
          className="h-72 w-full rounded-3xl object-cover shadow-lg lg:h-96"
        />
      </section>

      <section className="py-10">
        <h2 className="text-xl font-bold text-walnut">Six styles, one quiz</h2>
        <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {STYLES.map((s) => (
            <Card key={s.id} className="overflow-hidden">
              <img src={s.image} alt={`${s.label} style`} width={320} height={200} loading="lazy" className="h-24 w-full object-cover" />
              <p className="px-3 py-2 text-sm font-semibold">{s.label}</p>
            </Card>
          ))}
        </div>
      </section>
    </div>
  );
}
