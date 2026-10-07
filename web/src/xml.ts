/**
 * Text for XML documents the site writes (the Atom feeds, the graph's GraphML): escaped,
 * and without the characters XML 1.0 refuses even escaped, which would make a reader
 * (a feed reader, Gephi, NetworkX) refuse the whole file.
 */

/**
 * Whether XML 1.0 takes a character, escaped or not: not control characters (but tab and
 * line breaks), halves of surrogate pairs, or U+FFFE and U+FFFF.
 */
function isXmlChar(char: string): boolean {
  const code = char.codePointAt(0) ?? 0;
  return (
    code === 0x9 ||
    code === 0xa ||
    code === 0xd ||
    (code >= 0x20 && code < 0xd800) ||
    (code >= 0xe000 && code <= 0xfffd) ||
    code >= 0x10000
  );
}

/** Text for an XML element or a quoted attribute. */
export function xmlText(text: string): string {
  return [...text]
    .filter(isXmlChar)
    .join("")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
