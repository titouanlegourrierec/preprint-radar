/** Format an ISO date or timestamp as a short, locale-aware day, e.g. "25 Sept 2026". */
export function formatDay(iso: string): string {
  const date = iso.length === 10 ? new Date(`${iso}T00:00:00`) : new Date(iso);
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** Subject code from its full name, e.g. "Robotics (cs.RO)" -> "cs.RO". */
export function subjectCode(subject: string): string {
  return /\(([^()]+)\)\s*$/.exec(subject)?.[1] ?? subject;
}

/** Format an ISO date as a short day with its weekday, e.g. "Tue 8 Sept". */
export function formatShortDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}
