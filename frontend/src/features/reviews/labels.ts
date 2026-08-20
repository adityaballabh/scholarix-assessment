/** "top ID", then "top 3 IDs" — for phrases already led by a word. */
export function countedNoun(
  count: number,
  singular: string,
  plural: string,
): string {
  return count === 1 ? singular : `${count} ${plural}`;
}

/** "1 publication", then "58 publications" — for a count standing alone. */
export function pluralNoun(
  count: number,
  singular: string,
  plural: string,
): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
