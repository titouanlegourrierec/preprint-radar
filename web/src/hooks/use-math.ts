import { useEffect, useState } from "preact/hooks";
import { drawableTex } from "../math";

/** A formula's TeX drawn as MathML; throws on TeX it cannot read (UX-69). */
export type DrawFormula = (tex: string) => string;

let drawer: DrawFormula | null = null;
let loading: Promise<DrawFormula> | null = null;

// Temml, a chunk of its own (60 kB gzipped), asked for once a page shows a formula: most
// pages show none, and the landing page never waits for it.
function loadDrawer(): Promise<DrawFormula> {
  loading ??= import("temml").then(({ default: temml }) => {
    drawer = (tex) => temml.renderToString(drawableTex(tex), { throwOnError: true });
    return drawer;
  });
  return loading;
}

/**
 * What draws formulas, loaded once `wanted` (the text shown holds one); `null` until then,
 * and for good if it cannot load: the formulas stay written between their dollars.
 */
export function useFormulaDrawer(wanted: boolean): DrawFormula | null {
  const [draw, setDraw] = useState<DrawFormula | null>(drawer);
  useEffect(() => {
    if (!wanted || draw !== null) return;
    let live = true;
    loadDrawer()
      .then((loaded) => {
        if (live) setDraw(() => loaded);
      })
      .catch(() => {
        // Offline or a stale chunk: the formulas stay as written.
      });
    return () => {
      live = false;
    };
  }, [wanted, draw]);
  return draw;
}
