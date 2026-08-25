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

type RelativeUnit = "minute" | "hour" | "day" | "month" | "year";

function relativeAge(iso: string): { value: number; unit: RelativeUnit } {
  const minutes = Math.max(
    1,
    Math.floor((Date.now() - new Date(iso).getTime()) / 60000),
  );
  if (minutes < 60) return { value: minutes, unit: "minute" };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { value: hours, unit: "hour" };
  const days = Math.floor(hours / 24);
  if (days < 30) return { value: days, unit: "day" };
  const months = Math.floor(days / 30);
  if (months < 12) return { value: months, unit: "month" };
  return { value: Math.floor(months / 12), unit: "year" };
}

export function formatRelativeTime(iso: string): string {
  const { value, unit } = relativeAge(iso);
  return `${value} ${value === 1 ? unit : `${unit}s`} ago`;
}

export function compactRelativeParts(iso: string | null): {
  value: string;
  unit: string | null;
} {
  if (!iso) return { value: "—", unit: null };
  const { value, unit } = relativeAge(iso);
  const suffix: Record<RelativeUnit, string> = {
    minute: "min",
    hour: "h",
    day: "d",
    month: "mo",
    year: "yr",
  };
  return { value: String(value), unit: suffix[unit] };
}

export function formatFetchedAt(iso: string | null): string | null {
  if (!iso) return null;
  return formatLocalDateTime(iso);
}

export function formatEventTime(iso: string): string {
  return formatLocalDateTime(iso);
}
