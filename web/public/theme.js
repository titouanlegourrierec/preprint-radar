// Restore the theme chosen with the toggle (see src/preferences.ts) before first paint, and
// give the browser's bar its color: the forced scheme's in both metas (src/theme-color.ts).
// A file rather than an inline script, which the Content-Security-Policy refuses (SEC-1).
try {
  const theme = localStorage.getItem("preprint-radar:theme");
  if (theme === "light" || theme === "dark") {
    document.documentElement.dataset.theme = theme;
    const metas = [...document.querySelectorAll('meta[name="theme-color"]')];
    const forced = metas.find((meta) => meta.getAttribute("media")?.includes(theme));
    if (forced) for (const meta of metas) meta.content = forced.content;
  }
} catch {
  // Storage may be disabled; the system scheme then applies.
}
