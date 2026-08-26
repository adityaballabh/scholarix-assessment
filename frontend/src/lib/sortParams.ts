export function updateSortParams(
  previous: URLSearchParams,
  column: string,
  direction: "asc" | "desc" | null,
): URLSearchParams {
  const params = new URLSearchParams(previous);
  params.delete("dir");

  if (direction === null) {
    params.delete("sort");
    return params;
  }

  params.set("sort", column);
  if (direction === "asc") params.set("dir", "asc");
  return params;
}
