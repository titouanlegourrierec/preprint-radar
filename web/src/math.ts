/**
 * The LaTeX formulas of titles and abstracts (UX-69), which arXiv keeps between dollars: the
 * pipeline makes the rest plain text and leaves a formula that still holds markup as it is
 * (`latex.plain_text`), so "ResNet$^2$" or "$\mathcal{O}(N^2)$". The site draws them as
 * MathML (`components/MathText.tsx`), the browser's own, which loads no font and sets no
 * inline style the Content-Security-Policy would refuse.
 */

/** A piece of a text: words, or a formula's TeX between its dollars (without them). */
export interface TextPiece {
  text: string;
  math: boolean;
}

// A formula between single dollars, as Pandoc reads them: the opening one before a non-space,
// the closing one after a non-space and before no digit, so that "$20,000 and $30,000" stay
// words; or between double dollars. Never across an escaped dollar ("\$5").
const FORMULA_RE = /(?<!\\)\$\$([^$]+?)\$\$|(?<![\\$])\$(?![\s$])([^$]*?[^\s\\$])\$(?![\d$])/g;

/** The words and formulas of a text, in order; one piece of words when it holds none. */
export function textPieces(text: string): TextPiece[] {
  const pieces: TextPiece[] = [];
  let at = 0;
  for (const match of text.matchAll(FORMULA_RE)) {
    const start = match.index;
    if (start > at) pieces.push({ text: text.slice(at, start), math: false });
    pieces.push({ text: match[1] ?? match[2] ?? "", math: true });
    at = start + match[0].length;
  }
  if (at < text.length || pieces.length === 0) pieces.push({ text: text.slice(at), math: false });
  return pieces;
}

// A percent sign, where TeX starts a comment: arXiv writes "\%", which the pipeline makes
// plain (`latex.plain_text`), and "$86{-}98%$" would lose its end.
const PERCENT_RE = /(?<!\\)%/g;

/** A formula's TeX as it is drawn: its percent signs escaped. */
export function drawableTex(tex: string): string {
  return tex.replace(PERCENT_RE, "\\%");
}

// MathML's own attributes only: a style attribute written as HTML is one the site's
// Content-Security-Policy refuses ("style-src" without inline styles), which Temml sets on
// accents, colors and negative spaces, all three dispensable.
const STYLE_ATTRIBUTE_RE = /\sstyle="[^"]*"/g;

/** MathML as the site inserts it: without the style attributes its policy refuses. */
export function withoutStyles(mathml: string): string {
  return mathml.replace(STYLE_ATTRIBUTE_RE, "");
}
