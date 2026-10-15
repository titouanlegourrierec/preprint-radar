import type { ThemePreference } from "./preferences";

/** The page's background, `--bg` of each palette of styles.css (tests/styles.test.ts). */
export const BACKGROUNDS = { light: "#f7f7f5", dark: "#121212" } as const;

/** A `<meta name="theme-color">` of index.html: one per scheme, named by its `media`. */
interface ThemeColorMeta {
  content: string;
  getAttribute(name: string): string | null;
}

/**
 * Colors the browser's bar as the page (UX-18): each meta its own scheme's background while
 * the theme follows the system, both the forced scheme's when the toggle forces one.
 * `public/theme.js` does the same before first paint.
 */
export function applyThemeColor(metas: Iterable<ThemeColorMeta>, theme: ThemePreference): void {
  for (const meta of metas) {
    const scheme = meta.getAttribute("media")?.includes("dark") ? "dark" : "light";
    meta.content = BACKGROUNDS[theme === "auto" ? scheme : theme];
  }
}
