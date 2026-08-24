function formatLocalDateTime(iso: string): string {
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return iso;
  const date = value.toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });
  const year =
    value.getFullYear() === new Date().getFullYear()
      ? null
      : value.getFullYear();
  const time = value.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
  return year === null ? `${date} ${time}` : `${date} ${year}, ${time}`;
}

export function formatFetchedAt(iso: string | null): string | null {
  if (!iso) return null;
  return formatLocalDateTime(iso);
}

export function formatEventTime(iso: string): string {
  return formatLocalDateTime(iso);
}
