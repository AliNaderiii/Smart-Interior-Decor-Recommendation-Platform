import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/lib/types";
import { tokenStore, usingCookieAuth } from "@/lib/api";

interface AuthState {
  user: User | null;
  setAuth: (user: User, access: string, refresh: string) => void;
  setUser: (user: User) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      setAuth: (user, access, refresh) => {
        // Stage 03 (T-11): when the backend has issued httpOnly cookies the
        // tokens are already held out of JavaScript's reach. Persisting a
        // second copy in localStorage would re-open the exfiltration path the
        // cookies closed, and that copy outlives the session. Only the Bearer
        // fallback (`USE_COOKIE_AUTH=false`) keeps tokens client-side.
        if (usingCookieAuth()) {
          tokenStore.clear();
        } else {
          tokenStore.set(access, refresh);
        }
        set({ user });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        tokenStore.clear();
        set({ user: null });
      },
    }),
    {
      name: "sd_auth",
      // Persist the profile only. Nothing credential-shaped belongs in a
      // storage area every script on the origin can read.
      partialize: (state) => ({ user: state.user }),
    },
  ),
);
