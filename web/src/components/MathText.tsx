import { type DrawFormula, useFormulaDrawer } from "../hooks/use-math";
import { textPieces, withoutStyles } from "../math";
import { Highlighted } from "./Highlighted";

interface Props {
  text: string;
  terms: readonly string[];
}

/**
 * A title's or an abstract's words, search terms highlighted, and its formulas drawn as
 * MathML once Temml has loaded (UX-69): written between their dollars until then, and for
 * one it cannot read.
 */
export function MathText({ text, terms }: Props) {
  const pieces = textPieces(text);
  const draw = useFormulaDrawer(pieces.some((piece) => piece.math));
  return (
    <>
      {pieces.map((piece, index) =>
        piece.math ? (
          <Formula key={index} tex={piece.text} draw={draw} />
        ) : (
          <Highlighted key={index} text={piece.text} terms={terms} />
        ),
      )}
    </>
  );
}

// Each formula drawn once a page: the same few ("^2", "ℓ_1") recur across cards.
const drawn = new Map<string, string | null>();

function Formula({ tex, draw }: { tex: string; draw: DrawFormula | null }) {
  let mathml = draw === null ? null : drawn.get(tex);
  if (draw !== null && mathml === undefined) {
    try {
      mathml = withoutStyles(draw(tex));
    } catch {
      mathml = null;
    }
    drawn.set(tex, mathml);
  }
  if (!mathml) return <>{`$${tex}$`}</>;
  // MathML Temml drew from TeX: its text escaped, links refused (no `trust`), styles dropped.
  return <span class="math" dangerouslySetInnerHTML={{ __html: mathml }} />;
}
