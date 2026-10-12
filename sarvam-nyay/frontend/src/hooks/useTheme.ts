/**
 * useTheme — applies the persisted theme to <html>.
 *
 * Side effects:
 *   - Adds/removes the `dark` class on document.documentElement.
 *   - Listens to `prefers-color-scheme` changes when the user is in "system"
 *     mode so the app follows the OS automatically.
 *
 * Returns the resolved boolean so consumers (e.g. Recharts colour pickers)
 * can react to it.
 */

import { useEffect } from "react";
import { resolveTheme, useThemeStore } from "@/store/themeStore";

export function useTheme(): { isDark: boolean } {
  const mode = useThemeStore((s) => s.mode);

  useEffect(() => {
    const apply = (): void => {
      const resolved = resolveTheme(mode);
      const root = document.documentElement;
      if (resolved === "dark") root.classList.add("dark");
      else root.classList.remove("dark");
      root.dataset.theme = resolved;
    };
    apply();

    // Follow system changes only when the user has not pinned a preference.
    if (mode === "system" && typeof window !== "undefined" && window.matchMedia) {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      const onChange = (): void => apply();
      mq.addEventListener("change", onChange);
      return () => mq.removeEventListener("change", onChange);
    }
    return undefined;
  }, [mode]);

  return { isDark: resolveTheme(mode) === "dark" };
}
