import { useEffect, useState } from "preact/hooks";
import { trendsOf } from "../data";
import { type TopicNote, type TrendsFile, topicNote, topicOfQuery } from "../trends";

/**
 * What the Trends view's lists say of the topic a search names (PROD-20): rising, cooling or
 * new, from `trends.json`, asked for once a search is typed in a view that shows the note;
 * `null` for any other search.
 */
export function useTopicNote(
  category: string | undefined,
  query: string,
  shown: boolean,
): TopicNote | null {
  const key = shown ? topicOfQuery(query) : null;
  const wanted = key !== null && category !== undefined;
  const [held, setHeld] = useState<{ category: string; file: TrendsFile | null } | null>(null);
  useEffect(() => {
    if (!wanted || category === undefined) return;
    let live = true;
    void trendsOf(category).then((file) => {
      if (live) setHeld({ category, file });
    });
    return () => {
      live = false;
    };
  }, [wanted, category]);
  if (key === null || held === null || held.category !== category || held.file === null) {
    return null;
  }
  return topicNote(held.file, key);
}
