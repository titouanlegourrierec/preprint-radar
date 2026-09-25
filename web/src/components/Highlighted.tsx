import { highlight } from "../highlight";

interface Props {
  text: string;
  terms: readonly string[];
}

/** Render text with the words matching `terms` wrapped in `<mark>`. */
export function Highlighted({ text, terms }: Props) {
  return (
    <>
      {highlight(text, terms).map((segment, index) =>
        segment.match ? <mark key={index}>{segment.text}</mark> : segment.text,
      )}
    </>
  );
}
