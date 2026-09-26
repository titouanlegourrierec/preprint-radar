import { useEffect, useState } from "preact/hooks";
import { loadTheme, saveTheme, type ThemePreference } from "../preferences";

const DARK_SCHEME = "(prefers-color-scheme: dark)";
const CYCLE: Record<ThemePreference, ThemePreference> = {
  auto: "light",
  light: "dark",
  dark: "auto",
};

/**
 * The theme preference, applied as `data-theme` on <html> (index.html restores it before
 * first paint) and remembered in this browser. `resolved` is the scheme shown right now:
 * it also tracks the system scheme while the preference is "auto", so canvas drawings
 * can re-read their colors. `cycle` advances auto → light → dark, previewed by `next`.
 */
function apply(theme: ThemePreference): void {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
}

export function useTheme() {
  const [theme, setTheme] = useState<ThemePreference>(loadTheme);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(DARK_SCHEME).matches);

  useEffect(() => {
    const media = window.matchMedia(DARK_SCHEME);
    const onChange = () => setSystemDark(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => saveTheme(theme), [theme]);

  const resolved: "light" | "dark" = theme === "auto" ? (systemDark ? "dark" : "light") : theme;
  return {
    theme,
    resolved,
    next: CYCLE[theme],
    cycle: () =>
      setTheme((current) => {
        // Applied before the re-render: effects that re-read the CSS variables (the
        // graph canvas) run before an effect here would have set the attribute.
        const nextTheme = CYCLE[current];
        apply(nextTheme);
        return nextTheme;
      }),
  };
}
