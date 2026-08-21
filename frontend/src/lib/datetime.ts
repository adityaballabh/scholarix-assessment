const months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ");

export function formatFetchedAt(iso: string | null): string | null {
  if (!iso) return null;

  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(iso);
  if (!match) return iso;

  const [, year, month, day, hour, minute] = match;
  return `${months[Number(month) - 1] ?? month} ${Number(day)} ${year} ${hour}:${minute} UTC`;
}

export function formatEventTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
