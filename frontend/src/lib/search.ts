const TOKEN_SEPARATOR = /[^\p{L}\p{N}]+/u;

function fold(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function foldText(text: string): string[] {
  return fold(text).split(TOKEN_SEPARATOR).filter(Boolean);
}

// Token-prefix match over folded text, so "gonza mejia" finds "González de Mejía"
export function matchesAuthorName(authorName: string, query: string): boolean {
  const nameTokens = foldText(authorName);

  return foldText(query).every((queryToken) =>
    nameTokens.some((nameToken) => nameToken.startsWith(queryToken)),
  );
}

export function matchesNote(note: string, query: string): boolean {
  const haystack = fold(note);

  return query
    .split(/\s+/)
    .filter(Boolean)
    .every((word) => haystack.includes(fold(word)));
}
