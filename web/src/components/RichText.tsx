import { linkify } from "../linkify";
import { MathText } from "./MathText";

interface Props {
  text: string;
  terms: readonly string[];
}

/** Text with clickable URLs, highlighted search terms and drawn formulas (UX-69). */
export function RichText({ text, terms }: Props) {
  return (
    <>
      {linkify(text).map((part, index) =>
        part.url ? (
          <a key={index} href={part.url} target="_blank" rel="noopener noreferrer">
            {part.text}
          </a>
        ) : (
          <MathText key={index} text={part.text} terms={terms} />
        ),
      )}
    </>
  );
}
