/**
 * themeStore — persisted light/dark theme preference.
 *
 * Three states:
 *   - "system" : follow the OS `prefers-color-scheme` setting (default for new users)
 *   - "light"  : force light
 *   - "dark"   : force dark
 *
 * The `effective` getter returns the resolved boolean (true = dark) so
 * consumers don't have to re-evaluate the system preference themselves.
 */

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ThemeMode = "system" | "light" | "dark";

interface ThemeState {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  toggle: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: "system",
      setMode: (m) => set({ mode: m }),
      toggle: () => {
        const current = get().mode;
        // Cycle: system → dark → light → system (skip "system" if user has
        // already engaged the toggle once)
        if (current === "system") {
          set({ mode: prefersDark() ? "light" : "dark" });
        } else if (current === "dark") {
          set({ mode: "light" });
        } else {
          set({ mode: "dark" });
        }
      },
    }),
    {
      name: "veridictum-theme",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

export function prefersDark(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Returns the effective dark/light state given the current mode + system. */
export function resolveTheme(mode: ThemeMode): "light" | "dark" {
  if (mode === "system") return prefersDark() ? "dark" : "light";
  return mode;
}
