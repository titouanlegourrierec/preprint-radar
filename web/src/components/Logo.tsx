import { DOT, LOCKUP_VIEW_BOX, MARK_PATH, NAME_PATH, NAME_TRANSFORM } from "../logo";

/**
 * The logo in the top bar (UX-48), inline so that it takes the page's colors, the text's
 * and the accent's (`currentColor`, `.site-logo__dot`), in either theme, which an `<img>`
 * would not. Named once, for screen readers: no other label goes beside it.
 */
export function Lockup() {
  return (
    <svg viewBox={LOCKUP_VIEW_BOX} fill="currentColor" role="img" aria-label="Preprint Radar">
      <title>Preprint Radar</title>
      <path fill-rule="evenodd" d={MARK_PATH} />
      <g transform={NAME_TRANSFORM}>
        <path d={NAME_PATH} />
        <circle class="site-logo__dot" cx={DOT.cx} cy={DOT.cy} r={DOT.r} />
      </g>
    </svg>
  );
}
