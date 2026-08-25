import { matchesAuthorName, matchesNote } from "./search";

const AUTHOR_NAME = "María González de Mejía";
const REVIEW_NOTE = "Affiliation differs, but the publication topics overlap.";

describe("matchesAuthorName", () => {
  it("matches folded token prefixes in any order", () => {
    expect(matchesAuthorName(AUTHOR_NAME, "mejia gonza")).toBe(true);
  });

  it("requires every query token to match a name token", () => {
    expect(matchesAuthorName(AUTHOR_NAME, "maria larson")).toBe(false);
  });
});

describe("matchesNote", () => {
  it("matches folded words regardless of order", () => {
    expect(matchesNote(REVIEW_NOTE, "topics affiliation")).toBe(true);
  });

  it("rejects a query with a missing word", () => {
    expect(matchesNote(REVIEW_NOTE, "topics confirmed")).toBe(false);
  });
});
