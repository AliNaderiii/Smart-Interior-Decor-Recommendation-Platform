import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { post } from "@/lib/api";
import { useQuizStore } from "@/stores/quizStore";
import { useAuthStore } from "@/stores/authStore";
import {
  BUDGET_MAX,
  BUDGET_MIN,
  MATERIALS,
  PALETTE_PRESETS,
  STYLES,
} from "@/lib/constants";
import { Button, Card, Input } from "@/components/ui";
import { BudgetHistogram } from "@/components/BudgetHistogram";
import { celebrate } from "@/lib/celebrate";
import { useToast } from "@/components/Toast";
import { useCommands } from "@/components/CommandPalette";
import { spring } from "@/lib/motion";
import clsx from "clsx";
import { OptimizedImage } from "@/components/OptimizedImage";

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
  const toast = useToast();
  const reduce = useReducedMotion();

  const step = quiz.step;

  useCommands(
    [
      { id: "quiz.next", label: "Quiz: next step", group: "Actions", run: () => quiz.setStep(Math.min(4, quiz.step + 1)) },
      { id: "quiz.back", label: "Quiz: previous step", group: "Actions", run: () => quiz.setStep(Math.max(0, quiz.step - 1)) },
      { id: "quiz.style", label: "Jump to style", group: "Navigate", keywords: "step 1", run: () => quiz.setStep(0) },
      { id: "quiz.budget", label: "Jump to budget", group: "Navigate", keywords: "step 4 price", run: () => quiz.setStep(3) },
    ],
    [quiz.step],
  );

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
      // Genuine milestone — the user finished the whole flow.
      void celebrate();
      navigate(`/recommendations?quiz=${created.id}`);
    } catch (e: unknown) {
      const err = e as { body?: { error?: string }; message?: string };
      const msg = err.body?.error ?? err.message ?? "Could not save quiz";
      setError(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="h1 text-[var(--color-ink)]">Design your living room</h1>
      <p className="mt-1 text-sm text-[var(--color-muted)]">
        Step {step + 1} of 5 — {STEP_TITLES[step]}
      </p>

      {/* Stepper */}
      {/* Progress: the current segment shimmers so "where am I" is legible at
          a glance without reading the step counter. */}
      <ol className="mt-6 flex gap-1.5" aria-label={`Quiz progress: step ${step + 1} of ${STEP_TITLES.length}`}>
        {STEP_TITLES.map((title, i) => (
          <li
            key={title}
            aria-current={i === step ? "step" : undefined}
            className={clsx(
              "relative h-1.5 flex-1 overflow-hidden rounded-full transition-colors",
              i < step && "bg-[var(--color-accent)]",
              i === step && "bg-[var(--color-accent)]/30",
              i > step && "bg-[var(--color-line)]",
            )}
          >
            <span className="sr-only">{title}</span>
            {i === step && (
              <span className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-[var(--color-accent)] to-transparent motion-reduce:hidden" />
            )}
          </li>
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
            <p className="mb-5 text-sm text-[var(--color-muted)]">
              Pick the rooms you are drawn to. We infer your style from what you choose —
              you never have to name it.
            </p>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {STYLES.map((s) => {
                const active = quiz.styles.includes(s.id);
                return (
                  <motion.button
                    key={s.id}
                    type="button"
                    onClick={() => quiz.toggleStyle(s.id)}
                    aria-pressed={active}
                    whileHover={reduce ? undefined : { y: -2 }}
                    whileTap={reduce ? undefined : { scale: 0.98 }}
                    transition={spring}
                    className={clsx(
                      "group relative aspect-[5/4] overflow-hidden rounded-2xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2",
                      active
                        ? "ring-2 ring-[var(--color-accent)] ring-offset-2"
                        : "ring-1 ring-[var(--color-line)]",
                    )}
                  >
                    <OptimizedImage
                      src={s.image}
                      alt={`${s.label} style living room`}
                      width={500}
                      height={400}
                      sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                      wrapperClassName="absolute inset-0 h-full w-full"
                    />
                    {/* Gradient scrim: guarantees the label stays legible over
                        any photograph, which a flat caption bar cannot. */}
                    <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/10 to-transparent" />
                    <div className="absolute inset-x-0 bottom-0 flex items-end justify-between p-4">
                      <div>
                        <span className="block text-base font-semibold text-white">{s.label}</span>
                        <span className="block text-xs text-white/70">{s.fa}</span>
                      </div>
                    </div>
                    <AnimatePresence>
                      {active && (
                        <motion.span
                          initial={reduce ? false : { scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          exit={reduce ? undefined : { scale: 0, opacity: 0 }}
                          transition={spring}
                          className="absolute right-3 top-3 grid h-8 w-8 place-items-center rounded-full bg-white shadow-lg"
                        >
                          <motion.svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                            <motion.path
                              d="M3.5 8.5l3 3 6-7"
                              stroke="#0F172A"
                              strokeWidth="2.2"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              initial={reduce ? false : { pathLength: 0 }}
                              animate={{ pathLength: 1 }}
                              transition={{ duration: 0.25, ease: "easeOut" }}
                            />
                          </motion.svg>
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </motion.button>
                );
              })}
            </div>
          </div>
        )}

        {step === 1 && (
          <div>
            <p className="mb-5 text-sm text-[var(--color-muted)]">Choose up to 5 colours for your palette.</p>
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
                      "h-12 w-12 rounded-full transition-transform focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)] focus-visible:ring-offset-2",
                      "ring-1 ring-inset ring-black/10 hover:scale-105",
                      active && "scale-110 ring-2 ring-[var(--color-accent)] ring-offset-2",
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
                className="h-10 w-14 cursor-pointer rounded-lg border border-[var(--color-line)]"
                onChange={(e) => quiz.toggleColor(e.target.value.toUpperCase())}
              />
              <div className="flex gap-1.5">
                {quiz.color_palette.map((hex) => (
                  <span key={hex} className="h-6 w-6 rounded-full border border-[var(--color-line)]" style={{ backgroundColor: hex }} title={hex} />
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
            <p className="text-sm text-[var(--color-muted)] sm:col-span-2">
              ≈ {((quiz.room_width_cm * quiz.room_length_cm) / 10000).toFixed(1)} m² — we use this in the 2D floorplan preview.
            </p>
          </div>
        )}

        {step === 3 && (
          <BudgetHistogram
            min={BUDGET_MIN}
            max={BUDGET_MAX}
            valueMin={quiz.budget_min_toman}
            valueMax={quiz.budget_max_toman}
            onChange={(lo, hi) => quiz.setBudget(lo, hi)}
          />
        )}

        {step === 4 && (
          <div>
            <p className="mb-5 text-sm text-[var(--color-muted)]">Which materials do you love? (optional)</p>
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
                      active
                        ? "border-[var(--color-accent)] bg-[var(--color-accent)]/5 text-[var(--color-ink)]"
                        : "border-[var(--color-line)] text-[var(--color-muted)] hover:border-[var(--color-faint)]",
                    )}
                  >
                    {m.label} <span className="text-xs text-[var(--color-muted)]">({m.fa})</span>
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
          <Button variant="accent" onClick={() => quiz.setStep(step + 1)} disabled={!canNext}>
            Next →
          </Button>
        ) : (
          <Button variant="accent" onClick={submit} disabled={busy}>
            {busy ? "Finding matches…" : "Get my recommendations"}
          </Button>
        )}
      </div>
    </div>
  );
}
