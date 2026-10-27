import { highlight } from "../highlight";

interface Props {
  text: string;
  terms: readonly string[];
}

/**
 * Render text with the words matching `terms` wrapped in `<mark>`, each keyed by where it
 * starts in the text: a mark already shown stays the same element when another word is
 * found, so that only new ones draw their stroke (UX-56).
 */
export function Highlighted({ text, terms }: Props) {
  let at = 0;
  return (
    <>
      {highlight(text, terms).map((segment) => {
        const start = at;
        at += segment.text.length;
        return segment.match ? <mark key={start}>{segment.text}</mark> : segment.text;
      })}
    </>
  );
}
