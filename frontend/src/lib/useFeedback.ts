/**
 * 👍/👎 feedback hook — V2 Phase 3.
 *
 * Optimistic by design (Linear: "optimistic updates instead of spinners").
 * The thumb flips instantly, the request goes out, and a failure rolls the
 * button back and surfaces a toast. Waiting ~200ms to acknowledge a thumb
 * makes the control feel broken.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { get, post } from "@/lib/api";
import { useToast } from "@/components/Toast";

export type FeedbackMap = Record<string, number>;

export function useFeedbackMap() {
  return useQuery({
    queryKey: ["feedback"],
    queryFn: () => get<FeedbackMap>("/feedback"),
    staleTime: 60_000,
  });
}

export function useSubmitFeedback() {
  const qc = useQueryClient();
  const toast = useToast();

  return useMutation({
    mutationFn: (vars: { productId: string; signal: 1 | -1; category?: string }) =>
      post<{ product_id: string; signal: number }>("/feedback", {
        product_id: vars.productId,
        signal: vars.signal,
        category: vars.category,
      }),

    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: ["feedback"] });
      const previous = qc.getQueryData<FeedbackMap>(["feedback"]) ?? {};
      const next = { ...previous };
      // Mirror the server's toggle semantics so the optimistic state matches
      // what the API will actually do.
      if (next[vars.productId] === vars.signal) delete next[vars.productId];
      else next[vars.productId] = vars.signal;
      qc.setQueryData(["feedback"], next);
      return { previous };
    },

    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(["feedback"], ctx.previous);
      toast.error("Could not save your feedback. Please try again.");
    },

    onSuccess: (_data, vars) => {
      // The ranking depends on feedback, so the cached recommendations are now
      // stale. Refetch so the user SEES the list change — that is the whole
      // point of the control.
      qc.invalidateQueries({ queryKey: ["recommend"] });
      if (vars.signal === -1) toast.success("Got it — we'll show fewer like this.");
    },
  });
}
