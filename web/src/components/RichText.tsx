import { linkify } from "../linkify";
import { Highlighted } from "./Highlighted";

interface Props {
  text: string;
  terms: readonly string[];
}

/** Text with clickable URLs and highlighted search terms. */
export function RichText({ text, terms }: Props) {
  return (
    <>
      {linkify(text).map((part, index) =>
        part.url ? (
          <a key={index} href={part.url} target="_blank" rel="noopener noreferrer">
            {part.text}
          </a>
        ) : (
          <Highlighted key={index} text={part.text} terms={terms} />
        ),
      )}
    </>
  );
}
