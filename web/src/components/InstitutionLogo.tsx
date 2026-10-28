/**
 * A major institution's logo before its name (PROD-23), one chosen by hand (`logos.json`),
 * on a white tile, which keeps dark marks readable in the dark theme. For the eye: the name
 * beside it says the institution. The image has no size of its own: it takes its file's
 * proportions within the tile (`.logo`), which keeps its place while it loads.
 */
export function InstitutionLogo({ src }: { src: string }) {
  return (
    <span class="logo" aria-hidden="true">
      <img src={src} alt="" decoding="async" />
    </span>
  );
}
