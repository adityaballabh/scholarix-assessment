export function countedNoun(
  count: number,
  singular: string,
  plural: string,
): string {
  return count === 1 ? singular : `${count} ${plural}`;
}

export function pluralNoun(
  count: number,
  singular: string,
  plural: string,
): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
