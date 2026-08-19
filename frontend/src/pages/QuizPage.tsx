import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { post } from "@/lib/api";
import { useQuizStore } from "@/stores/quizStore";
import { useAuthStore } from "@/stores/authStore";
import {
  BUDGET_MAX,
  BUDGET_MIN,
  MATERIALS,
  PALETTE_PRESETS,
  STYLES,
  formatToman,
} from "@/lib/constants";
import { Button, Card, Input } from "@/components/ui";
import clsx from "clsx";

const STEP_TITLES = ["Style", "Color Palette", "Room Dimensions", "Budget", "Materials"];

export default function QuizPage() {
  const quiz = useQuizStore();
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const projectId = params.get("project");
  const [clientName, setClientName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const step = quiz.step;

  const canNext =
    (step === 0 && quiz.styles.length > 0) ||
    (step === 1 && quiz.color_palette.length > 0) ||
    step === 2 ||
    (step === 3 && quiz.budget_max_toman > quiz.budget_min_toman) ||
    step === 4;

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const created = await post<{ id: string }>("/quiz", {
        styles: quiz.styles,
        color_palette: quiz.color_palette,
        room_width_cm: quiz.room_width_cm,
        room_length_cm: quiz.room_length_cm,
        budget_min_toman: quiz.budget_min_toman,
        budget_max_toman: quiz.budget_max_toman,
        materials: quiz.materials,
        patterns: quiz.patterns,
        project_id: projectId,
        client_name: clientName,
      });
      navigate(`/recommendations?quiz=${created.id}`);
    } catch (e: unknown) {
      const err = e as { response?: { data?: { error?: string } } };
      setError(err.response?.data?.error ?? "Could not save quiz");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-bold text-walnut">Design your living room</h1>
      <p className="mt-1 text-sm text-stone">
        Step {step + 1} of 5 — {STEP_TITLES[step]}
      </p>

      {/* Stepper */}
      <ol className="mt-4 flex gap-1" aria-label="Quiz progress">
        {STEP_TITLES.map((title, i) => (
          <li
            key={title}
            aria-current={i === step ? "step" : undefined}
            className={clsx("h-1.5 flex-1 rounded-full", i <= step ? "bg-clay" : "bg-sand")}
          />
        ))}
      </ol>

      {projectId && user?.role === "designer" && (
        <Card className="mt-6 p-4">
          <label htmlFor="client" className="mb-1 block text-sm font-medium">Client name (for this project)</label>
          <Input id="client" value={clientName} onChange={(e) => setClientName(e.target.value)} placeholder="e.g. Mr. Ahmadi" />
        </Card>
      )}

      <Card className="mt-6 p-6">
        {step === 0 && (
          <div>
            <p className="mb-4 text-sm text-stone">Pick up to 3 styles that speak to you.</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {STYLES.map((s) => {
                const active = quiz.styles.includes(s.id);
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => quiz.toggleStyle(s.id)}
                    aria-pressed={active}
                    className={clsx(
                      "group overflow-hidden rounded-2xl border-2 text-left transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-clay",
                      active ? "border-clay shadow-md" : "border-transparent hover:border-[#e5ded3]",
                    )}
                  >
                    <img
                      src={s.image}
                      alt={`${s.label} style living room`}
                      width={320}
                      height={200}
                      loading="lazy"
                      className="h-28 w-full object-cover"
                    />
                    <div className="flex items-center justify-between bg-white px-3 py-2">
                      <span className="text-sm font-semibold">{s.label}</span>
                      {active && <span className="text-clay">✓</span>}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {step === 1 && (
          <div>
            <p className="mb-4 text-sm text-stone">Choose up to 5 colors for your palette.</p>
            <div className="flex flex-wrap gap-3">
              {PALETTE_PRESETS.map((hex) => {
                const active = quiz.color_palette.includes(hex);
                return (
                  <button
                    key={hex}
                    type="button"
                    onClick={() => quiz.toggleColor(hex)}
                    aria-pressed={active}
                    aria-label={`Color ${hex}`}
                    className={clsx(
                      "h-12 w-12 rounded-full border-2 transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-clay",
                      active ? "scale-110 border-clay ring-2 ring-clay/40" : "border-[#e5ded3]",
                    )}
                    style={{ backgroundColor: hex }}
                  />
                );
              })}
            </div>
            <div className="mt-4 flex items-center gap-3">
              <label htmlFor="custom-color" className="text-sm font-medium">Custom:</label>
              <input
                id="custom-color"
                type="color"
                className="h-10 w-14 cursor-pointer rounded-lg border border-[#e5ded3]"
                onChange={(e) => quiz.toggleColor(e.target.value.toUpperCase())}
              />
              <div className="flex gap-1.5">
                {quiz.color_palette.map((hex) => (
                  <span key={hex} className="h-6 w-6 rounded-full border border-[#e5ded3]" style={{ backgroundColor: hex }} title={hex} />
                ))}
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="width" className="mb-1 block text-sm font-medium">Room width (cm)</label>
              <Input
                id="width" type="number" min={100} max={3000}
                value={quiz.room_width_cm}
                onChange={(e) => quiz.setDimensions(Number(e.target.value), quiz.room_length_cm)}
              />
            </div>
            <div>
              <label htmlFor="length" className="mb-1 block text-sm font-medium">Room length (cm)</label>
              <Input
                id="length" type="number" min={100} max={3000}
                value={quiz.room_length_cm}
                onChange={(e) => quiz.setDimensions(quiz.room_width_cm, Number(e.target.value))}
              />
            </div>
            <p className="text-sm text-stone sm:col-span-2">
              ≈ {((quiz.room_width_cm * quiz.room_length_cm) / 10000).toFixed(1)} m² — we use this in the 2D floorplan preview.
            </p>
          </div>
        )}

        {step === 3 && (
          <div>
            <p className="mb-1 text-sm font-medium">Total budget range</p>
            <p className="mb-4 text-lg font-bold text-clay-dark">
              {formatToman(quiz.budget_min_toman)} — {formatToman(quiz.budget_max_toman)}
            </p>
            <label htmlFor="bmin" className="block text-xs text-stone">Minimum</label>
            <input
              id="bmin" type="range" min={BUDGET_MIN} max={BUDGET_MAX} step={1_000_000}
              value={quiz.budget_min_toman}
              onChange={(e) =>
                quiz.setBudget(
                  Math.min(Number(e.target.value), quiz.budget_max_toman - 1_000_000),
                  quiz.budget_max_toman,
                )
              }
              className="w-full accent-clay"
            />
            <label htmlFor="bmax" className="mt-3 block text-xs text-stone">Maximum</label>
            <input
              id="bmax" type="range" min={BUDGET_MIN} max={BUDGET_MAX} step={1_000_000}
              value={quiz.budget_max_toman}
              onChange={(e) =>
                quiz.setBudget(
                  quiz.budget_min_toman,
                  Math.max(Number(e.target.value), quiz.budget_min_toman + 1_000_000),
                )
              }
              className="w-full accent-clay"
            />
          </div>
        )}

        {step === 4 && (
          <div>
            <p className="mb-4 text-sm text-stone">Which materials do you love? (optional)</p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {MATERIALS.map((m) => {
                const active = quiz.materials.includes(m.id);
                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => quiz.toggleMaterial(m.id)}
                    aria-pressed={active}
                    className={clsx(
                      "rounded-xl border-2 px-4 py-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-clay",
                      active ? "border-clay bg-[#fdf3ee] text-clay-dark" : "border-[#e5ded3] hover:border-stone",
                    )}
                  >
                    {m.label} <span className="text-xs text-stone">({m.fa})</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </Card>

      {error && <p className="mt-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}

      <div className="mt-6 flex justify-between">
        <Button variant="secondary" onClick={() => quiz.setStep(Math.max(0, step - 1))} disabled={step === 0}>
          ← Back
        </Button>
        {step < 4 ? (
          <Button onClick={() => quiz.setStep(step + 1)} disabled={!canNext}>
            Next →
          </Button>
        ) : (
          <Button onClick={submit} disabled={busy}>
            {busy ? "Finding matches…" : "Get my recommendations ✨"}
          </Button>
        )}
      </div>
    </div>
  );
}
