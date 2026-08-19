import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/lib/types";
import { tokenStore } from "@/lib/api";

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
        tokenStore.set(access, refresh);
        set({ user });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        tokenStore.clear();
        set({ user: null });
      },
    }),
    { name: "sd_auth" },
  ),
);
