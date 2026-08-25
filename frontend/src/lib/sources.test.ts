import { FETCH_SOURCE_ORDER, sourceLabel } from "./sources";

it("uses consistent labels for evidence sources and fetch stages", () => {
  expect(sourceLabel("semantic_scholar")).toBe("Semantic Scholar");
  expect(sourceLabel("openalex_author_publications")).toBe(
    "OpenAlex author publications",
  );
  expect(FETCH_SOURCE_ORDER[FETCH_SOURCE_ORDER.length - 1]).toBe(
    "case_generation",
  );
});

it("makes an unknown source identifier readable", () => {
  expect(sourceLabel("new_source")).toBe("new source");
});
