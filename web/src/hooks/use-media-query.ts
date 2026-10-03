import { useEffect, useState } from "preact/hooks";

/** Whether the media query matches now, following changes (a window resized, rotated). */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    list.addEventListener("change", onChange);
    onChange();
    return () => list.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}
